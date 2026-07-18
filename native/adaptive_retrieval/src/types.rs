use pyo3::prelude::*;
use serde::{Deserialize, Serialize};

use crate::error::{Result, RetrievalError};

#[pyclass(frozen, get_all, from_py_object)]
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct IndexManifest {
    pub schema_version: u32,
    pub version: String,
    pub corpus_hash: String,
    pub embedding_provider: String,
    pub embedding_model: String,
    pub dimensions: usize,
    pub normalization: String,
}

#[pymethods]
impl IndexManifest {
    #[new]
    #[pyo3(signature = (
        schema_version,
        version,
        corpus_hash,
        embedding_provider,
        embedding_model,
        dimensions,
        normalization = "l2".to_owned()
    ))]
    #[allow(clippy::too_many_arguments)]
    fn py_new(
        schema_version: u32,
        version: String,
        corpus_hash: String,
        embedding_provider: String,
        embedding_model: String,
        dimensions: usize,
        normalization: String,
    ) -> Self {
        Self {
            schema_version,
            version,
            corpus_hash,
            embedding_provider,
            embedding_model,
            dimensions,
            normalization,
        }
    }
}

impl IndexManifest {
    pub fn validate(&self) -> Result<()> {
        if self.schema_version != 1 {
            return Err(RetrievalError::InvalidManifest(
                "schema_version must be 1".to_owned(),
            ));
        }
        if self.dimensions == 0 {
            return Err(RetrievalError::InvalidManifest(
                "dimensions must be positive".to_owned(),
            ));
        }
        if self.normalization != "l2" {
            return Err(RetrievalError::InvalidManifest(
                "normalization must be l2".to_owned(),
            ));
        }
        for (name, value) in [
            ("version", &self.version),
            ("corpus_hash", &self.corpus_hash),
            ("embedding_provider", &self.embedding_provider),
            ("embedding_model", &self.embedding_model),
        ] {
            if value.trim().is_empty() {
                return Err(RetrievalError::InvalidManifest(format!(
                    "{name} must not be empty"
                )));
            }
        }
        Ok(())
    }

    pub fn fingerprint(&self) -> String {
        format!(
            "{}:{}:{}:{}:{}:{}:{}",
            self.schema_version,
            self.version,
            self.corpus_hash,
            self.embedding_provider,
            self.embedding_model,
            self.dimensions,
            self.normalization
        )
    }
}

#[pyclass(frozen, get_all, from_py_object)]
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ChunkRecord {
    pub chunk_id: String,
    pub tenant_id: String,
    pub text: String,
    pub source_uri: String,
    pub vector: Vec<f32>,
}

#[pymethods]
impl ChunkRecord {
    #[new]
    fn py_new(
        chunk_id: String,
        tenant_id: String,
        text: String,
        source_uri: String,
        vector: Vec<f32>,
    ) -> Self {
        Self {
            chunk_id,
            tenant_id,
            text,
            source_uri,
            vector,
        }
    }
}

#[pyclass(frozen, get_all, skip_from_py_object)]
#[derive(Clone, Debug, PartialEq)]
pub struct SearchHit {
    pub chunk_id: String,
    pub source_uri: String,
    pub text: String,
    pub dense_score: Option<f32>,
    pub dense_rank: Option<usize>,
    pub bm25_score: Option<f32>,
    pub bm25_rank: Option<usize>,
    pub rrf_score: f32,
}

#[pyclass(frozen, get_all, skip_from_py_object)]
#[derive(Clone, Debug)]
pub struct IndexStats {
    pub version: String,
    pub chunk_count: usize,
    pub dimensions: usize,
}
