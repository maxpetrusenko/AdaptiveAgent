use std::collections::{HashMap, HashSet};
use std::fs::{self, File};
use std::io::Write;
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tantivy::schema::{Schema, STORED, STRING, TEXT};
use tantivy::{Index, IndexWriter, TantivyDocument};

use crate::error::{Result, RetrievalError};
use crate::scoring::normalize;
use crate::types::{ChunkRecord, IndexManifest};

const SNAPSHOT_FILE: &str = "snapshot.json";
const CURRENT_FILE: &str = "CURRENT";

#[derive(Deserialize, Serialize)]
struct StoredSnapshot {
    manifest: IndexManifest,
    chunks: Vec<ChunkRecord>,
}

pub struct LoadedSnapshot {
    pub manifest: IndexManifest,
    pub chunks: Vec<ChunkRecord>,
    pub chunks_by_id: HashMap<String, ChunkRecord>,
    pub index: Index,
}

pub fn build_snapshot(
    root: &Path,
    manifest: IndexManifest,
    mut chunks: Vec<ChunkRecord>,
) -> Result<LoadedSnapshot> {
    manifest.validate()?;
    validate_and_normalize_chunks(&manifest, &mut chunks)?;
    chunks.sort_by(|left, right| left.chunk_id.cmp(&right.chunk_id));

    fs::create_dir_all(root.join("versions")).map_err(persistence_error)?;
    let version_key = version_key(&manifest);
    let final_dir = root.join("versions").join(&version_key);
    if !final_dir.exists() {
        let staging = root
            .join("versions")
            .join(format!(".building-{version_key}-{}", unique_suffix()));
        fs::create_dir_all(&staging).map_err(persistence_error)?;
        write_snapshot(&staging, &manifest, &chunks)?;
        fs::rename(&staging, &final_dir).map_err(persistence_error)?;
    } else {
        let stored = read_stored_snapshot(&final_dir)?;
        validate_manifest(&manifest, &stored.manifest)?;
    }
    atomic_write(root, CURRENT_FILE, version_key.as_bytes())?;
    load_version(root, &version_key, &manifest)
}

pub fn load_current(root: &Path, expected: &IndexManifest) -> Result<LoadedSnapshot> {
    expected.validate()?;
    let current_path = root.join(CURRENT_FILE);
    let version_key = fs::read_to_string(&current_path).map_err(|error| {
        if error.kind() == std::io::ErrorKind::NotFound {
            RetrievalError::NotFound(current_path.display().to_string())
        } else {
            persistence_error(error)
        }
    })?;
    load_version(root, version_key.trim(), expected)
}

fn load_version(
    root: &Path,
    version_key: &str,
    expected: &IndexManifest,
) -> Result<LoadedSnapshot> {
    let version_dir = root.join("versions").join(version_key);
    let stored = read_stored_snapshot(&version_dir)?;
    validate_manifest(expected, &stored.manifest)?;
    let index = Index::open_in_dir(version_dir.join("tantivy")).map_err(search_error)?;
    let chunks_by_id = stored
        .chunks
        .iter()
        .cloned()
        .map(|chunk| (chunk.chunk_id.clone(), chunk))
        .collect();
    Ok(LoadedSnapshot {
        manifest: stored.manifest,
        chunks: stored.chunks,
        chunks_by_id,
        index,
    })
}

fn write_snapshot(
    directory: &Path,
    manifest: &IndexManifest,
    chunks: &[ChunkRecord],
) -> Result<()> {
    let snapshot = StoredSnapshot {
        manifest: manifest.clone(),
        chunks: chunks.to_vec(),
    };
    let payload = serde_json::to_vec_pretty(&snapshot)
        .map_err(|error| RetrievalError::Persistence(error.to_string()))?;
    write_synced(&directory.join(SNAPSHOT_FILE), &payload)?;
    write_tantivy_index(&directory.join("tantivy"), chunks)
}

fn read_stored_snapshot(directory: &Path) -> Result<StoredSnapshot> {
    let path = directory.join(SNAPSHOT_FILE);
    let payload = fs::read(&path).map_err(|error| {
        if error.kind() == std::io::ErrorKind::NotFound {
            RetrievalError::NotFound(path.display().to_string())
        } else {
            persistence_error(error)
        }
    })?;
    serde_json::from_slice(&payload).map_err(|error| RetrievalError::Persistence(error.to_string()))
}

fn write_tantivy_index(directory: &Path, chunks: &[ChunkRecord]) -> Result<()> {
    fs::create_dir_all(directory).map_err(persistence_error)?;
    let mut schema_builder = Schema::builder();
    let chunk_id = schema_builder.add_text_field("chunk_id", STRING | STORED);
    let tenant_id = schema_builder.add_text_field("tenant_id", STRING);
    let text = schema_builder.add_text_field("text", TEXT);
    let index = Index::create_in_dir(directory, schema_builder.build()).map_err(search_error)?;
    let mut writer: IndexWriter = index.writer(50_000_000).map_err(search_error)?;
    for chunk in chunks {
        let mut document = TantivyDocument::default();
        document.add_text(chunk_id, &chunk.chunk_id);
        document.add_text(tenant_id, &chunk.tenant_id);
        document.add_text(text, &chunk.text);
        writer.add_document(document).map_err(search_error)?;
    }
    writer.commit().map_err(search_error)?;
    writer.wait_merging_threads().map_err(search_error)
}

fn validate_and_normalize_chunks(
    manifest: &IndexManifest,
    chunks: &mut [ChunkRecord],
) -> Result<()> {
    let mut ids = HashSet::new();
    for chunk in chunks {
        if !ids.insert(chunk.chunk_id.clone()) {
            return Err(RetrievalError::InvalidManifest(format!(
                "duplicate chunk_id: {}",
                chunk.chunk_id
            )));
        }
        for (name, value) in [
            ("chunk_id", &chunk.chunk_id),
            ("tenant_id", &chunk.tenant_id),
            ("text", &chunk.text),
            ("source_uri", &chunk.source_uri),
        ] {
            if value.trim().is_empty() {
                return Err(RetrievalError::InvalidManifest(format!(
                    "{name} must not be empty"
                )));
            }
        }
        chunk.vector = normalize(&chunk.vector, manifest.dimensions)?;
    }
    Ok(())
}

pub fn validate_manifest(expected: &IndexManifest, actual: &IndexManifest) -> Result<()> {
    if expected != actual {
        return Err(RetrievalError::ManifestMismatch(format!(
            "expected {}, found {}",
            expected.fingerprint(),
            actual.fingerprint()
        )));
    }
    Ok(())
}

fn version_key(manifest: &IndexManifest) -> String {
    let digest = Sha256::digest(manifest.fingerprint().as_bytes());
    format!("{digest:x}")[..24].to_owned()
}

fn unique_suffix() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |duration| duration.as_nanos())
}

fn persistence_error(error: std::io::Error) -> RetrievalError {
    RetrievalError::Persistence(error.to_string())
}

fn write_synced(path: &Path, payload: &[u8]) -> Result<()> {
    let mut file = File::create(path).map_err(persistence_error)?;
    file.write_all(payload).map_err(persistence_error)?;
    file.sync_all().map_err(persistence_error)
}

fn atomic_write(directory: &Path, name: &str, payload: &[u8]) -> Result<()> {
    let temporary = directory.join(format!(".{name}-{}", unique_suffix()));
    write_synced(&temporary, payload)?;
    fs::rename(&temporary, directory.join(name)).map_err(persistence_error)?;
    File::open(directory)
        .and_then(|handle| handle.sync_all())
        .map_err(persistence_error)
}

fn search_error(error: tantivy::TantivyError) -> RetrievalError {
    RetrievalError::Search(error.to_string())
}
