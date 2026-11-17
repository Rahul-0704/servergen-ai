"""
ServerGen AI — PDF Document Parser.

Extracts text page-by-page from PDF documents using pypdf, tracking page
numbers and metadata while handling encryption and corrupt pages gracefully.
Includes native OCR fallback for scanned and screenshot documents.
"""

from __future__ import annotations

import io
import logging

from pypdf import PdfReader

from src.core.exceptions import ValidationError
from src.rag.parsers.base import BaseParser, ExtractedBlock, ParsedDocument

logger = logging.getLogger("servergen.rag.parsers.pdf")


def _run_ocr_on_image(img_bytes: bytes, timeout_secs: float = 20.0) -> str:
    """Run native OCR on an image byte buffer using Windows winocr or available OCR engine."""
    try:
        import asyncio
        import concurrent.futures

        from PIL import Image

        img = Image.open(io.BytesIO(img_bytes))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        def _do_recognize() -> str:
            try:
                import winocr

                res = asyncio.run(winocr.recognize_pil(img, "en-US"))
                return (res.text or "").strip()
            except ImportError:
                return ""
            except Exception as e:
                logger.debug("winocr recognition error: %s", e)
                return ""

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(_do_recognize).result(timeout=timeout_secs)
        else:
            return _do_recognize()
    except Exception as exc:
        logger.debug("OCR processing failed: %s", exc)
        return ""


class PDFParser(BaseParser):
    @property
    def name(self) -> str:
        return "pypdf_ocr_parser"

    def parse(self, content: bytes, filename: str) -> ParsedDocument:
        try:
            reader = PdfReader(io.BytesIO(content))
        except Exception as exc:
            raise ValidationError(f"Invalid or corrupt PDF document: {exc}") from exc

        if reader.is_encrypted:
            try:
                # Attempt empty password decrypt
                reader.decrypt("")
            except Exception as exc:
                raise ValidationError(
                    "Password-protected or encrypted PDFs are not supported"
                ) from exc

        blocks: list[ExtractedBlock] = []
        warnings: list[str] = []
        total_chars = 0
        has_embedded_images = False

        # Try to read document title from metadata
        doc_title = ""
        if reader.metadata and reader.metadata.title:
            doc_title = str(reader.metadata.title).strip()
        if not doc_title:
            doc_title = filename.rsplit(".", 1)[0]

        total_pages = len(reader.pages)
        if total_pages == 0:
            raise ValidationError("PDF has 0 pages")

        for idx, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
                text = text.replace("\r\n", "\n").replace("\r", "\n").strip()

                page_images = getattr(page, "images", [])
                if page_images and len(page_images) > 0:
                    has_embedded_images = True

                # If text is empty or very short, check for embedded images and perform OCR
                if len(text) < 40 and page_images and len(page_images) > 0:
                    ocr_chunks: list[str] = []
                    for img_obj in page_images:
                        ocr_txt = _run_ocr_on_image(img_obj.data)
                        if ocr_txt:
                            ocr_chunks.append(ocr_txt)
                    if ocr_chunks:
                        ocr_combined = "\n\n".join(ocr_chunks)
                        text = f"{text}\n\n{ocr_combined}".strip() if text else ocr_combined
                        warnings.append(
                            f"page_{idx}_ocr_applied: Extracted text via native OCR from "
                            f"{len(ocr_chunks)} embedded image(s)."
                        )

                if text:
                    total_chars += len(text)
                    blocks.append(
                        ExtractedBlock(
                            content=text,
                            page_number=idx,
                            section_heading=f"Page {idx}",
                            metadata={"page": idx, "total_pages": total_pages},
                        )
                    )
                elif page_images and len(page_images) > 0:
                    # Scanned page with images but no OCR text detected
                    desc = (
                        f"[Document Page {idx}: Scanned visual content "
                        f"({len(page_images)} image(s)) with no selectable text layer.]"
                    )
                    total_chars += len(desc)
                    blocks.append(
                        ExtractedBlock(
                            content=desc,
                            page_number=idx,
                            section_heading=f"Page {idx}",
                            metadata={"page": idx, "total_pages": total_pages, "scanned": True},
                        )
                    )
            except Exception as page_exc:
                logger.warning("Failed to extract page %d from %s: %s", idx, filename, page_exc)
                warnings.append(f"page_{idx}_extraction_warning: {page_exc}")

        if not blocks or total_chars == 0:
            if not has_embedded_images:
                msg = (
                    "PDF contains no extractable text. "
                    "Document may be scanned image-only or corrupt."
                )
                raise ValidationError(msg)
            blocks.append(
                ExtractedBlock(
                    content=(
                        f"[Document: {filename} ({total_pages} page(s)) contains scanned image "
                        "content with no extractable text.]"
                    ),
                    page_number=1,
                    section_heading="Document Summary",
                    metadata={"total_pages": total_pages, "scanned": True},
                )
            )
            total_chars = len(blocks[0].content)
            warnings.append(
                "scanned_image_pdf_fallback: No machine-readable text found in scanned images."
            )

        return ParsedDocument(
            blocks=blocks,
            title=doc_title,
            total_characters=total_chars,
            parser_name=self.name,
            warnings=warnings,
        )
