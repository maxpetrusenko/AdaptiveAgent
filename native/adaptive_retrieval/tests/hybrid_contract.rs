use adaptive_retrieval::{ChunkRecord, IndexManifest, RetrievalIndex};
use tempfile::tempdir;

fn manifest(version: &str, corpus_hash: &str) -> IndexManifest {
    IndexManifest {
        schema_version: 1,
        version: version.to_owned(),
        corpus_hash: corpus_hash.to_owned(),
        embedding_provider: "fixture".to_owned(),
        embedding_model: "fixture-v1".to_owned(),
        dimensions: 2,
        normalization: "l2".to_owned(),
    }
}

fn chunk(id: &str, tenant: &str, text: &str, vector: [f32; 2]) -> ChunkRecord {
    ChunkRecord {
        chunk_id: id.to_owned(),
        tenant_id: tenant.to_owned(),
        text: text.to_owned(),
        source_uri: format!("fixture://{id}"),
        vector: vector.to_vec(),
    }
}

#[test]
fn hybrid_search_is_tenant_scoped_and_deterministic() {
    let root = tempdir().unwrap();
    let index = RetrievalIndex::build(
        root.path(),
        manifest("v1", "corpus-a"),
        vec![
            chunk("a", "tenant-a", "durable checkpoint resume", [1.0, 0.0]),
            chunk("b", "tenant-a", "checkpoint ledger", [0.8, 0.2]),
            chunk("c", "tenant-b", "durable checkpoint resume", [1.0, 0.0]),
        ],
    )
    .unwrap();

    let hits = index
        .search("checkpoint", &[1.0, 0.0], "tenant-a", 10)
        .unwrap();

    assert_eq!(
        hits.iter()
            .map(|hit| hit.chunk_id.as_str())
            .collect::<Vec<_>>(),
        vec!["a", "b"]
    );
    assert!(hits[0].dense_rank.is_some());
    assert!(hits[0].bm25_rank.is_some());
    assert!(hits[0].rrf_score >= hits[1].rrf_score);
}

#[test]
fn equal_scores_use_chunk_id_as_final_tie_break() {
    let root = tempdir().unwrap();
    let index = RetrievalIndex::build(
        root.path(),
        manifest("v1", "corpus-tie"),
        vec![
            chunk("z-last", "tenant-a", "same", [1.0, 0.0]),
            chunk("a-first", "tenant-a", "same", [1.0, 0.0]),
        ],
    )
    .unwrap();

    let hits = index.search("same", &[1.0, 0.0], "tenant-a", 2).unwrap();
    assert_eq!(hits[0].chunk_id, "a-first");
    assert_eq!(hits[1].chunk_id, "z-last");
}

#[test]
fn manifest_mismatch_fails_closed() {
    let root = tempdir().unwrap();
    RetrievalIndex::build(
        root.path(),
        manifest("v1", "corpus-a"),
        vec![chunk("a", "tenant-a", "checkpoint", [1.0, 0.0])],
    )
    .unwrap();

    let error = RetrievalIndex::open(root.path(), &manifest("v1", "corpus-b"))
        .err()
        .expect("mismatch should fail");
    assert!(error.to_string().contains("manifest mismatch"));
}

#[test]
fn versioned_index_reopens_and_reload_switches_current_version() {
    let root = tempdir().unwrap();
    let mut first = RetrievalIndex::build(
        root.path(),
        manifest("v1", "corpus-a"),
        vec![chunk("a", "tenant-a", "first", [1.0, 0.0])],
    )
    .unwrap();

    let reopened = RetrievalIndex::open(root.path(), &manifest("v1", "corpus-a")).unwrap();
    assert_eq!(reopened.stats().version, "v1");

    RetrievalIndex::build(
        root.path(),
        manifest("v2", "corpus-b"),
        vec![chunk("b", "tenant-a", "second", [0.0, 1.0])],
    )
    .unwrap();

    let stats = first.reload(&manifest("v2", "corpus-b")).unwrap();
    assert_eq!(stats.version, "v2");
    let hits = first.search("second", &[0.0, 1.0], "tenant-a", 1).unwrap();
    assert_eq!(hits[0].chunk_id, "b");
}

#[test]
fn invalid_vectors_fail_before_persistence() {
    let root = tempdir().unwrap();
    let error = RetrievalIndex::build(
        root.path(),
        manifest("v1", "corpus-a"),
        vec![chunk("a", "tenant-a", "bad", [f32::NAN, 0.0])],
    )
    .err()
    .expect("invalid vector should fail");

    assert!(error.to_string().contains("invalid vector"));
    assert!(!root.path().join("CURRENT").exists());
}

#[test]
fn empty_generation_is_valid_and_returns_no_hits() {
    let root = tempdir().unwrap();
    let index =
        RetrievalIndex::build(root.path(), manifest("v-empty", "corpus-empty"), vec![]).unwrap();

    let hits = index
        .search("anything", &[1.0, 0.0], "tenant-a", 5)
        .unwrap();

    assert_eq!(index.stats().chunk_count, 0);
    assert!(hits.is_empty());
}
