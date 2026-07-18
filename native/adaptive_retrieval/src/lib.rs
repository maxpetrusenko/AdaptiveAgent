mod error;
mod index;
mod persistence;
mod scoring;
mod types;

use std::panic::{catch_unwind, AssertUnwindSafe};
use std::sync::{Arc, RwLock};

use error::{Result, RetrievalError};
pub use index::RetrievalIndex;
use pyo3::prelude::*;
pub use types::{ChunkRecord, IndexManifest, IndexStats, SearchHit};

#[pyclass(name = "HybridIndex")]
struct PyHybridIndex {
    inner: Arc<RwLock<RetrievalIndex>>,
}

#[pymethods]
impl PyHybridIndex {
    #[staticmethod]
    fn build(
        py: Python<'_>,
        root: String,
        manifest: IndexManifest,
        chunks: Vec<ChunkRecord>,
    ) -> PyResult<Self> {
        let index =
            py.detach(move || panic_safe(|| RetrievalIndex::build(root, manifest, chunks)))?;
        Ok(Self {
            inner: Arc::new(RwLock::new(index)),
        })
    }

    #[staticmethod]
    fn open(py: Python<'_>, root: String, expected: IndexManifest) -> PyResult<Self> {
        let index = py.detach(move || panic_safe(|| RetrievalIndex::open(root, &expected)))?;
        Ok(Self {
            inner: Arc::new(RwLock::new(index)),
        })
    }

    fn search(
        &self,
        py: Python<'_>,
        query_text: String,
        query_vector: Vec<f32>,
        tenant_id: String,
        limit: usize,
    ) -> PyResult<Vec<SearchHit>> {
        let inner = Arc::clone(&self.inner);
        py.detach(move || {
            panic_safe(|| {
                let index = inner
                    .read()
                    .map_err(|_| RetrievalError::Search("index lock poisoned".to_owned()))?;
                index.search(&query_text, &query_vector, &tenant_id, limit)
            })
        })
    }

    fn reload(&self, py: Python<'_>, expected: IndexManifest) -> PyResult<IndexStats> {
        let inner = Arc::clone(&self.inner);
        py.detach(move || {
            panic_safe(|| {
                let mut index = inner
                    .write()
                    .map_err(|_| RetrievalError::Search("index lock poisoned".to_owned()))?;
                index.reload(&expected)
            })
        })
    }

    fn stats(&self) -> PyResult<IndexStats> {
        let index = self
            .inner
            .read()
            .map_err(|_| RetrievalError::Search("index lock poisoned".to_owned()))?;
        Ok(index.stats())
    }
}

fn panic_safe<T>(operation: impl FnOnce() -> Result<T>) -> PyResult<T> {
    catch_unwind(AssertUnwindSafe(operation))
        .map_err(|_| RetrievalError::InternalPanic)?
        .map_err(Into::into)
}

#[pymodule]
fn adaptive_retrieval(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<IndexManifest>()?;
    module.add_class::<ChunkRecord>()?;
    module.add_class::<SearchHit>()?;
    module.add_class::<IndexStats>()?;
    module.add_class::<PyHybridIndex>()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::panic_safe;

    #[test]
    fn panic_safe_maps_panics_to_python_errors() {
        pyo3::Python::initialize();
        let error = panic_safe::<()>(|| panic!("ffi panic")).unwrap_err();
        assert!(error.to_string().contains("internal retrieval panic"));
    }
}
