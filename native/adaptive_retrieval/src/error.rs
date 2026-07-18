use pyo3::exceptions::{PyFileNotFoundError, PyRuntimeError, PyValueError};
use pyo3::PyErr;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum RetrievalError {
    #[error("invalid manifest: {0}")]
    InvalidManifest(String),
    #[error("manifest mismatch: {0}")]
    ManifestMismatch(String),
    #[error("invalid vector: {0}")]
    InvalidVector(String),
    #[error("index not found: {0}")]
    NotFound(String),
    #[error("persistence error: {0}")]
    Persistence(String),
    #[error("search error: {0}")]
    Search(String),
    #[error("internal retrieval panic")]
    InternalPanic,
}

pub type Result<T> = std::result::Result<T, RetrievalError>;

impl From<RetrievalError> for PyErr {
    fn from(error: RetrievalError) -> Self {
        match error {
            RetrievalError::InvalidManifest(_)
            | RetrievalError::ManifestMismatch(_)
            | RetrievalError::InvalidVector(_) => PyValueError::new_err(error.to_string()),
            RetrievalError::NotFound(_) => PyFileNotFoundError::new_err(error.to_string()),
            RetrievalError::Persistence(_)
            | RetrievalError::Search(_)
            | RetrievalError::InternalPanic => PyRuntimeError::new_err(error.to_string()),
        }
    }
}
