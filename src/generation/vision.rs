//! Immutable, operator-provisioned PNG bundles. No request-supplied paths or URLs.
use super::Config;
use base64::{Engine, engine::general_purpose::STANDARD};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{collections::BTreeMap, fs::File, io::Read, path::Path};

const MAX_IMAGES: usize = 8 * 1024 * 1024;
pub(super) const MAX_OUTBOUND: usize = 12 * 1024 * 1024;
pub(super) fn hash(bytes: &[u8]) -> String {
    ring::digest::digest(&ring::digest::SHA256, bytes)
        .as_ref()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}
pub(super) fn is_hash(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct InputEvidence {
    pub reference_sha256: String,
    pub image_sha256: Vec<String>,
}
impl InputEvidence {
    pub(super) fn valid(&self) -> bool {
        is_hash(&self.reference_sha256)
            && (1..=8).contains(&self.image_sha256.len())
            && self.image_sha256.iter().all(|s| is_hash(s))
    }
}
#[derive(Clone, Debug, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
struct PageReference {
    page: usize,
    sha256: String,
    bytes: usize,
    width: u32,
    height: u32,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Reference {
    schema_version: u32,
    kind: String,
    document_id: String,
    native_source_sha256: String,
    inspector_manifest_sha256: String,
    prompt: String,
    pages: Vec<PageReference>,
}
#[derive(Deserialize)]
struct Manifest {
    schema_version: u32,
    complete: bool,
    publication_approved: bool,
    document_id: String,
    native_source_sha256: String,
    coordinate_unit: String,
    pages: Vec<Page>,
}
#[derive(Deserialize)]
struct Page {
    page: usize,
    file: String,
    sha256: String,
    bytes: usize,
    width: u32,
    height: u32,
}
struct FrozenPage {
    reference: PageReference,
    url: String,
}
struct Bundle {
    document_id: String,
    native_hash: String,
    pages: Vec<FrozenPage>,
}
pub(super) struct Registry(BTreeMap<String, Bundle>);
fn read(path: &Path, limit: usize) -> Result<Vec<u8>, &'static str> {
    if std::fs::symlink_metadata(path)
        .map_err(|_| "vision_asset_unavailable")?
        .file_type()
        .is_symlink()
    {
        return Err("vision_symlink_refused");
    }
    let file = File::open(path).map_err(|_| "vision_asset_unavailable")?;
    if !file
        .metadata()
        .map_err(|_| "vision_asset_unavailable")?
        .is_file()
    {
        return Err("vision_asset_not_file");
    }
    let mut bytes = Vec::new();
    file.take(limit as u64 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "vision_asset_read_failed")?;
    if bytes.len() > limit {
        return Err("vision_asset_bound_exceeded");
    }
    Ok(bytes)
}
impl Registry {
    pub(super) fn load(config: &Config) -> Result<Self, &'static str> {
        let mut bundles = BTreeMap::new();
        let mut total = 0;
        for (expected, root) in &config.vision_bundles {
            if std::fs::symlink_metadata(root)
                .map_err(|_| "vision_bundle_unavailable")?
                .file_type()
                .is_symlink()
            {
                return Err("vision_symlink_refused");
            }
            let raw = read(&root.join("manifest.json"), 1024 * 1024)?;
            if hash(&raw) != *expected {
                return Err("vision_manifest_hash_mismatch");
            }
            let m: Manifest =
                serde_json::from_slice(&raw).map_err(|_| "invalid_vision_manifest")?;
            if m.schema_version != 1
                || !m.complete
                || m.publication_approved
                || m.coordinate_unit != "source_page_pixels"
                || !super::label(&m.document_id, 256)
                || !is_hash(&m.native_source_sha256)
                || !(1..=32).contains(&m.pages.len())
            {
                return Err("invalid_vision_manifest");
            }
            let mut pages = Vec::new();
            for (i, p) in m.pages.into_iter().enumerate() {
                if p.page != i + 1
                    || p.file != format!("page-{}.png", i + 1)
                    || !is_hash(&p.sha256)
                    || p.width == 0
                    || p.height == 0
                    || u64::from(p.width) * u64::from(p.height) > 16_000_000
                {
                    return Err("invalid_vision_page");
                }
                let bytes = read(&root.join(&p.file), MAX_IMAGES - total)?;
                total += bytes.len();
                if bytes.len() != p.bytes
                    || hash(&bytes) != p.sha256
                    || bytes.len() < 24
                    || &bytes[..8] != b"\x89PNG\r\n\x1a\n"
                    || &bytes[12..16] != b"IHDR"
                    || bytes[16..20] != p.width.to_be_bytes()
                    || bytes[20..24] != p.height.to_be_bytes()
                {
                    return Err("vision_page_mismatch");
                }
                let url = format!("data:image/png;base64,{}", STANDARD.encode(&bytes));
                pages.push(FrozenPage {
                    reference: PageReference {
                        page: p.page,
                        sha256: p.sha256,
                        bytes: p.bytes,
                        width: p.width,
                        height: p.height,
                    },
                    url,
                });
            }
            bundles.insert(
                expected.clone(),
                Bundle {
                    document_id: m.document_id,
                    native_hash: m.native_source_sha256,
                    pages,
                },
            );
        }
        Ok(Self(bundles))
    }
    pub(super) fn content(&self, input: &str) -> Result<(Value, InputEvidence), &'static str> {
        let r: Reference = serde_json::from_str(input).map_err(|_| "invalid_vision_reference")?;
        if r.schema_version != 1
            || r.kind != "vision_reference_v1"
            || r.prompt.trim().is_empty()
            || r.prompt.len() > 8192
            || !(1..=8).contains(&r.pages.len())
        {
            return Err("invalid_vision_reference");
        }
        let bundle = self
            .0
            .get(&r.inspector_manifest_sha256)
            .ok_or("unknown_vision_bundle")?;
        if r.document_id != bundle.document_id || r.native_source_sha256 != bundle.native_hash {
            return Err("vision_source_mismatch");
        }
        let mut parts = vec![json!({"type":"text","text":r.prompt})];
        let mut seen = Vec::new();
        let mut hashes = Vec::new();
        for p in r.pages {
            if seen.contains(&p.page) {
                return Err("duplicate_vision_page");
            }
            let page = p
                .page
                .checked_sub(1)
                .and_then(|n| bundle.pages.get(n))
                .ok_or("unknown_vision_page")?;
            if page.reference != p {
                return Err("vision_reference_mismatch");
            }
            seen.push(p.page);
            hashes.push(p.sha256);
            parts.push(json!({"type":"image_url","image_url":{"url":page.url}}));
        }
        Ok((
            Value::Array(parts),
            InputEvidence {
                reference_sha256: hash(input.as_bytes()),
                image_sha256: hashes,
            },
        ))
    }
}
