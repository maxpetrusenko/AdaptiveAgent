use adaptive_retrieval::{ChunkRecord, IndexManifest, RetrievalIndex};
use criterion::{criterion_group, criterion_main, Criterion};
use tempfile::tempdir;

fn search_benchmark(c: &mut Criterion) {
    let root = tempdir().unwrap();
    let manifest = IndexManifest {
        schema_version: 1,
        version: "bench-v1".to_owned(),
        corpus_hash: "bench-corpus".to_owned(),
        embedding_provider: "fixture".to_owned(),
        embedding_model: "fixture-v1".to_owned(),
        dimensions: 32,
        normalization: "l2".to_owned(),
    };
    let chunks = (0..1_000)
        .map(|index| ChunkRecord {
            chunk_id: format!("chunk-{index:04}"),
            tenant_id: "tenant-a".to_owned(),
            text: format!("durable retrieval checkpoint {index}"),
            source_uri: format!("fixture://{index}"),
            vector: vec![1.0; 32],
        })
        .collect();
    let index = RetrievalIndex::build(root.path(), manifest, chunks).unwrap();

    c.bench_function("hybrid_search_1k_32d", |bencher| {
        bencher.iter(|| {
            index
                .search("checkpoint", &[1.0; 32], "tenant-a", 10)
                .unwrap()
        })
    });
}

criterion_group!(benches, search_benchmark);
criterion_main!(benches);
