use std::path::{Path, PathBuf};

use tantivy::collector::TopDocs;
use tantivy::query::{BooleanQuery, Occur, Query, QueryParser, TermQuery};
use tantivy::schema::{IndexRecordOption, Value};
use tantivy::{ReloadPolicy, TantivyDocument, Term};

use crate::error::{Result, RetrievalError};
use crate::persistence::{build_snapshot, load_current, LoadedSnapshot};
use crate::scoring::{dense_ranking, normalize, reciprocal_rank_fusion, score_order};
use crate::types::{ChunkRecord, IndexManifest, IndexStats, SearchHit};

pub struct RetrievalIndex {
    root: PathBuf,
    snapshot: LoadedSnapshot,
}

impl RetrievalIndex {
    pub fn build(
        root: impl AsRef<Path>,
        manifest: IndexManifest,
        chunks: Vec<ChunkRecord>,
    ) -> Result<Self> {
        let root = root.as_ref().to_path_buf();
        let snapshot = build_snapshot(&root, manifest, chunks)?;
        Ok(Self { root, snapshot })
    }

    pub fn open(root: impl AsRef<Path>, expected: &IndexManifest) -> Result<Self> {
        let root = root.as_ref().to_path_buf();
        let snapshot = load_current(&root, expected)?;
        Ok(Self { root, snapshot })
    }

    pub fn reload(&mut self, expected: &IndexManifest) -> Result<IndexStats> {
        self.snapshot = load_current(&self.root, expected)?;
        Ok(self.stats())
    }

    pub fn search(
        &self,
        query_text: &str,
        query_vector: &[f32],
        tenant_id: &str,
        limit: usize,
    ) -> Result<Vec<SearchHit>> {
        if tenant_id.trim().is_empty() {
            return Err(RetrievalError::Search(
                "tenant_id must not be empty".to_owned(),
            ));
        }
        if limit == 0 {
            return Err(RetrievalError::Search("limit must be positive".to_owned()));
        }
        let query = normalize(query_vector, self.snapshot.manifest.dimensions)?;
        let tenant_count = self
            .snapshot
            .chunks
            .iter()
            .filter(|chunk| chunk.tenant_id == tenant_id)
            .count();
        if tenant_count == 0 {
            return Ok(Vec::new());
        }
        let candidate_limit = tenant_count.min(limit.saturating_mul(4).max(32));
        let dense = dense_ranking(&self.snapshot.chunks, &query, tenant_id, candidate_limit);
        let lexical = self.lexical_ranking(query_text, tenant_id, tenant_count)?;
        Ok(reciprocal_rank_fusion(
            &self.snapshot.chunks_by_id,
            &dense,
            &lexical,
            limit,
        ))
    }

    pub fn stats(&self) -> IndexStats {
        IndexStats {
            version: self.snapshot.manifest.version.clone(),
            chunk_count: self.snapshot.chunks.len(),
            dimensions: self.snapshot.manifest.dimensions,
        }
    }

    fn lexical_ranking(
        &self,
        query_text: &str,
        tenant: &str,
        tenant_count: usize,
    ) -> Result<Vec<(String, f32)>> {
        if query_text.trim().is_empty() {
            return Ok(Vec::new());
        }
        let schema = self.snapshot.index.schema();
        let chunk_field = schema
            .get_field("chunk_id")
            .map_err(|error| RetrievalError::Search(error.to_string()))?;
        let tenant_field = schema
            .get_field("tenant_id")
            .map_err(|error| RetrievalError::Search(error.to_string()))?;
        let text_field = schema
            .get_field("text")
            .map_err(|error| RetrievalError::Search(error.to_string()))?;
        let reader = self
            .snapshot
            .index
            .reader_builder()
            .reload_policy(ReloadPolicy::Manual)
            .try_into()
            .map_err(|error: tantivy::TantivyError| RetrievalError::Search(error.to_string()))?;
        let searcher = reader.searcher();
        let text_query = QueryParser::for_index(&self.snapshot.index, vec![text_field])
            .parse_query(&escape_query(query_text))
            .map_err(|error| RetrievalError::Search(error.to_string()))?;
        let tenant_query = TermQuery::new(
            Term::from_field_text(tenant_field, tenant),
            IndexRecordOption::Basic,
        );
        let query = BooleanQuery::new(vec![
            (Occur::Must, text_query),
            (Occur::Must, Box::new(tenant_query) as Box<dyn Query>),
        ]);
        let top_docs = searcher
            .search(&query, &TopDocs::with_limit(tenant_count).order_by_score())
            .map_err(|error| RetrievalError::Search(error.to_string()))?;
        let mut ranked = Vec::with_capacity(top_docs.len());
        for (score, address) in top_docs {
            let document: TantivyDocument = searcher
                .doc(address)
                .map_err(|error| RetrievalError::Search(error.to_string()))?;
            let chunk_id = document
                .get_first(chunk_field)
                .and_then(|value| value.as_str())
                .ok_or_else(|| RetrievalError::Search("missing stored chunk_id".to_owned()))?;
            ranked.push((chunk_id.to_owned(), score));
        }
        ranked.sort_by(score_order);
        Ok(ranked)
    }
}

fn escape_query(query: &str) -> String {
    const RESERVED: [char; 17] = [
        '+', '^', '`', ':', '{', '}', '[', ']', '(', ')', '"', '~', '*', '?', '|', '&', '!',
    ];
    let mut escaped = String::with_capacity(query.len());
    for character in query.chars() {
        if character == '\\' || RESERVED.contains(&character) {
            escaped.push('\\');
        }
        escaped.push(character);
    }
    escaped
}
