"""
Image Mapper — Export Phase helper.

Extracts all content images from a PDF via PyMuPDF, assigns them stable
filenames (pN_iM.ext), saves them to disk, and returns a per-page manifest
that maps page numbers to ordered lists of ImageEntry objects.

The manifest is used by export_book.py to replace Docling's generic
`<!-- image -->` placeholders with resolved `<!-- image: path -->` tags,
giving every image a traceable identity before the text reaches the parser.

Filtering strategy
------------------
PDFs embed many non-content images: page borders, hairline rules, logos,
watermarks, small decorative dots.  We filter on two axes:

  1. Pixel dimensions  — both width and height must be >= MIN_PX (default 60).
     This kills single-pixel borders and sub-icon decorations.

  2. Image aspect ratio — we reject images that are extremely wide-and-flat
     (w/h > MAX_ASPECT, e.g. 15) or extremely tall-and-narrow (h/w > MAX_ASPECT).
     These are almost always horizontal/vertical rule graphics.

  3. Duplicate xref     — Docling may reference the same embedded image object
     multiple times (e.g. a repeated logo on every page).  We track xrefs and
     only save the first occurrence; subsequent pages reference the same file.

Reading order
-------------
Within a page, images are sorted by their bounding-box top-left corner:
  primary key   = y0  (top of image — vertical reading order)
  secondary key = x0  (left edge   — left-to-right within the same row)

This matches Docling's rendering order so the N-th `<!-- image -->` in a
page's markdown corresponds to the N-th ImageEntry for that page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.core.logger import logger

# ── Defaults ───────────────────────────────────────────────────────────────

MIN_PX: int    = 60     # minimum width AND height in pixels
MAX_ASPECT: float = 12.0  # reject if max_dim / min_dim > this (hairline rules)


# ── Data model ─────────────────────────────────────────────────────────────

@dataclass
class ImageEntry:
    """Metadata for one extracted image."""
    file: str            # Relative path from export_dir, e.g. "images/p5_i1.png"
    page: int            # 1-indexed page number
    order: int           # 0-indexed position within the page (reading order)
    x0: float            # Bounding box — used for reading-order sorting
    y0: float
    x1: float
    y1: float
    width_px: int        # Pixel dimensions of the extracted raster
    height_px: int


# page_num (1-indexed) → list[ImageEntry] sorted by (y0, x0)
PageImageManifest = dict[int, list[ImageEntry]]


# ── Public API ─────────────────────────────────────────────────────────────

def build_image_manifest(
    doc,                          # fitz.Document (imported by caller)
    img_dir: Path,
    min_px: int = MIN_PX,
    max_aspect: float = MAX_ASPECT,
    page_from: int = 1,
    page_to: Optional[int] = None,
) -> PageImageManifest:
    """
    Walk pages *page_from* through *page_to* of *doc*, extract qualifying
    images to *img_dir*, and return a PageImageManifest.

    Parameters
    ----------
    doc        : open fitz.Document
    img_dir    : directory where image files will be saved (must exist)
    min_px     : minimum pixel dimension for both width and height
    max_aspect : maximum w/h or h/w ratio; images above this are hairlines
    page_from  : first page to scan, 1-indexed (default: 1)
    page_to    : last page to scan, 1-indexed inclusive (default: last page)

    Returns
    -------
    PageImageManifest — {page_num: [ImageEntry, ...] sorted by reading order}
    """
    import fitz  # imported lazily so the module is importable without fitz

    total = len(doc)
    first = max(0, page_from - 1)          # convert to 0-indexed
    last  = min(total - 1, (page_to or total) - 1)

    manifest: PageImageManifest = {}
    seen_xrefs: dict[int, str] = {}
    saved_count = 0
    skipped_count = 0

    for page_idx in range(first, last + 1):
        page_num = page_idx + 1
        page: fitz.Page = doc[page_idx]

        # get_images(full=True) returns:
        #   (xref, smask, width, height, bpc, colorspace, alt_colorspace,
        #    name, filter, referencer)
        raw_images = page.get_images(full=True)
        if not raw_images:
            continue

        # Build a lookup: image xref → bounding rect on this page
        # We use page.get_image_rects() which returns a list of Rect per image.
        xref_to_rects: dict[int, list] = {}
        for img_info in raw_images:
            xref = img_info[0]
            try:
                rects = page.get_image_rects(xref)
                xref_to_rects[xref] = rects if rects else []
            except Exception:
                xref_to_rects[xref] = []

        page_entries: list[ImageEntry] = []

        for img_info in raw_images:
            xref        = img_info[0]
            img_width   = img_info[2]   # pixel width of stored image
            img_height  = img_info[3]   # pixel height

            # ── Size filter ───────────────────────────────────────────────
            if img_width < min_px or img_height < min_px:
                skipped_count += 1
                logger.debug(
                    f"  Skip p{page_num} xref={xref}: "
                    f"too small ({img_width}×{img_height}px)"
                )
                continue

            # ── Aspect-ratio filter ───────────────────────────────────────
            aspect = max(img_width, img_height) / max(min(img_width, img_height), 1)
            if aspect > max_aspect:
                skipped_count += 1
                logger.debug(
                    f"  Skip p{page_num} xref={xref}: "
                    f"hairline aspect {aspect:.1f} ({img_width}×{img_height}px)"
                )
                continue

            # ── Get bounding rect for this occurrence ─────────────────────
            rects = xref_to_rects.get(xref, [])
            if rects:
                r = rects[0]   # first occurrence on this page
                x0, y0, x1, y1 = r.x0, r.y0, r.x1, r.y1
            else:
                # Fallback: place at top-left so it still sorts predictably
                x0 = y0 = x1 = y1 = 0.0

            # ── Dedup: reuse filename if xref already saved ───────────────
            if xref in seen_xrefs:
                rel_path = seen_xrefs[xref]
                logger.debug(
                    f"  Reuse p{page_num} xref={xref} → {rel_path}"
                )
            else:
                # Extract and save image
                try:
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    ext = base_image.get("ext", "png")
                    # img_dir relative to export_dir, e.g. export/images/p5_i1.png
                    img_idx = saved_count + 1
                    filename = f"p{page_num}_i{img_idx}.{ext}"
                    abs_path = img_dir / filename
                    abs_path.write_bytes(image_bytes)
                    rel_path = f"images/{filename}"
                    seen_xrefs[xref] = rel_path
                    saved_count += 1
                    logger.debug(f"  Saved p{page_num} xref={xref} → {rel_path}")
                except Exception as exc:
                    skipped_count += 1
                    logger.warning(
                        f"  Failed to extract p{page_num} xref={xref}: {exc}"
                    )
                    continue

            page_entries.append(ImageEntry(
                file=rel_path,
                page=page_num,
                order=0,          # filled in after sorting
                x0=x0, y0=y0, x1=x1, y1=y1,
                width_px=img_width,
                height_px=img_height,
            ))

        # Sort by reading order (top→bottom, left→right) and assign order index
        page_entries.sort(key=lambda e: (e.y0, e.x0))
        for idx, entry in enumerate(page_entries):
            entry.order = idx

        if page_entries:
            manifest[page_num] = page_entries

    logger.info(
        f"Image manifest: {saved_count} saved, "
        f"{skipped_count} skipped, "
        f"{len(manifest)} pages with images"
    )
    return manifest


def resolve_image_tags(
    full_text: str,
    manifest: PageImageManifest,
) -> str:
    """
    Replace generic `<!-- image -->` placeholders in *full_text* with
    resolved `<!-- image: path -->` tags using the page manifest.

    The function relies on `<!-- pages X-Y -->` section markers that
    export_book.py inserts between Docling batches.  Within each section
    it knows which pages are covered, collects all images for those pages
    in reading order, and replaces each `<!-- image -->` left-to-right.

    Mismatch handling
    -----------------
    * Fewer images than tags  → excess tags become `<!-- image: UNRESOLVED -->`
    * More images than tags   → extra images are appended as additional tags
      at the END of the section, so they are not silently dropped.
    """
    import re

    _RE_PAGE_MARKER = re.compile(r"<!--\s*pages\s+(\d+)-(\d+)\s*-->")
    _RE_IMAGE_BARE  = re.compile(r"<!--\s*image\s*-->")

    # Split text into sections delimited by <!-- pages X-Y --> markers
    # We keep the delimiters by using a capturing group.
    parts = re.split(r"(<!--\s*pages\s+\d+-\d+\s*-->)", full_text)

    output_parts: list[str] = []
    current_range: Optional[tuple[int, int]] = None

    for part in parts:
        m_marker = _RE_PAGE_MARKER.match(part.strip())
        if m_marker:
            # This part IS a page marker — record range, keep as-is
            current_range = (int(m_marker.group(1)), int(m_marker.group(2)))
            output_parts.append(part)
            continue

        if current_range is None:
            # Before the first page marker (preamble) — leave untouched
            output_parts.append(part)
            continue

        # Collect images for this page range in reading order
        start_page, end_page = current_range
        section_images: list[str] = []
        for pn in range(start_page, end_page + 1):
            for entry in manifest.get(pn, []):
                section_images.append(entry.file)

        # Count bare <!-- image --> tags in this section
        tag_count = len(_RE_IMAGE_BARE.findall(part))

        if tag_count == 0 and not section_images:
            output_parts.append(part)
            continue

        # Log mismatch
        if tag_count != len(section_images):
            logger.warning(
                f"Pages {start_page}-{end_page}: "
                f"{tag_count} <!-- image --> tag(s) vs "
                f"{len(section_images)} image(s) in manifest"
            )

        img_iter = iter(section_images)

        def _replace_one(match: re.Match) -> str:  # noqa: ANN202
            try:
                path = next(img_iter)
                return f"<!-- image: {path} -->"
            except StopIteration:
                return "<!-- image: UNRESOLVED -->"

        resolved = _RE_IMAGE_BARE.sub(_replace_one, part)

        # Append any extra manifest images not covered by a tag
        leftover = list(img_iter)
        if leftover:
            extras = "\n".join(f"<!-- image: {p} -->" for p in leftover)
            resolved = resolved.rstrip("\n") + "\n" + extras + "\n"
            logger.debug(
                f"Pages {start_page}-{end_page}: "
                f"appended {len(leftover)} extra image tag(s)"
            )

        output_parts.append(resolved)

    return "".join(output_parts)
