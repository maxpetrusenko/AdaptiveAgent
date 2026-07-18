use std::cmp::Ordering;
use std::collections::HashMap;

use rayon::prelude::*;

use crate::error::{Result, RetrievalError};
use crate::types::{ChunkRecord, SearchHit};

const RRF_K: f32 = 60.0;

pub fn normalize(values: &[f32], dimensions: usize) -> Result<Vec<f32>> {
    if values.len() != dimensions {
        return Err(RetrievalError::InvalidVector(format!(
            "expected {dimensions} dimensions, received {}",
            values.len()
        )));
    }
    if values.iter().any(|value| !value.is_finite()) {
        return Err(RetrievalError::InvalidVector(
            "values must be finite".to_owned(),
        ));
    }
    let norm_squared: f32 = values.iter().map(|value| value * value).sum();
    if !norm_squared.is_finite() || norm_squared <= f32::EPSILON {
        return Err(RetrievalError::InvalidVector(
            "vector norm must be positive and finite".to_owned(),
        ));
    }
    let inverse_norm = norm_squared.sqrt().recip();
    Ok(values.iter().map(|value| value * inverse_norm).collect())
}

pub fn dense_ranking(
    chunks: &[ChunkRecord],
    query: &[f32],
    tenant_id: &str,
    candidate_limit: usize,
) -> Vec<(String, f32)> {
    let mut ranked: Vec<_> = chunks
        .par_iter()
        .filter(|chunk| chunk.tenant_id == tenant_id)
        .map(|chunk| {
            let score: f32 = chunk
                .vector
                .iter()
                .zip(query)
                .map(|(left, right)| left * right)
                .sum();
            (chunk.chunk_id.clone(), score)
        })
        .collect();
    ranked.sort_by(|left, right| {
        right
            .1
            .total_cmp(&left.1)
            .then_with(|| left.0.cmp(&right.0))
    });
    ranked.truncate(candidate_limit);
    ranked
}

#[derive(Default)]
struct FusedHit {
    dense_score: Option<f32>,
    dense_rank: Option<usize>,
    bm25_score: Option<f32>,
    bm25_rank: Option<usize>,
    rrf_score: f32,
}

pub fn reciprocal_rank_fusion(
    chunks: &HashMap<String, ChunkRecord>,
    dense: &[(String, f32)],
    lexical: &[(String, f32)],
    limit: usize,
) -> Vec<SearchHit> {
    let mut fused = HashMap::<String, FusedHit>::new();
    for (offset, (chunk_id, score)) in dense.iter().enumerate() {
        let rank = offset + 1;
        let entry = fused.entry(chunk_id.clone()).or_default();
        entry.dense_score = Some(*score);
        entry.dense_rank = Some(rank);
        entry.rrf_score += 1.0 / (RRF_K + rank as f32);
    }
    for (offset, (chunk_id, score)) in lexical.iter().enumerate() {
        let rank = offset + 1;
        let entry = fused.entry(chunk_id.clone()).or_default();
        entry.bm25_score = Some(*score);
        entry.bm25_rank = Some(rank);
        entry.rrf_score += 1.0 / (RRF_K + rank as f32);
    }

    let mut results: Vec<_> = fused
        .into_iter()
        .filter_map(|(chunk_id, scores)| {
            let chunk = chunks.get(&chunk_id)?;
            Some(SearchHit {
                chunk_id,
                source_uri: chunk.source_uri.clone(),
                text: chunk.text.clone(),
                dense_score: scores.dense_score,
                dense_rank: scores.dense_rank,
                bm25_score: scores.bm25_score,
                bm25_rank: scores.bm25_rank,
                rrf_score: scores.rrf_score,
            })
        })
        .collect();
    results.sort_by(|left, right| {
        right
            .rrf_score
            .total_cmp(&left.rrf_score)
            .then_with(|| best_rank(left).cmp(&best_rank(right)))
            .then_with(|| left.chunk_id.cmp(&right.chunk_id))
    });
    results.truncate(limit);
    results
}

fn best_rank(hit: &SearchHit) -> usize {
    match (hit.dense_rank, hit.bm25_rank) {
        (Some(dense), Some(bm25)) => dense.min(bm25),
        (Some(dense), None) => dense,
        (None, Some(bm25)) => bm25,
        (None, None) => usize::MAX,
    }
}

pub fn score_order(left: &(String, f32), right: &(String, f32)) -> Ordering {
    right
        .1
        .total_cmp(&left.1)
        .then_with(|| left.0.cmp(&right.0))
}
