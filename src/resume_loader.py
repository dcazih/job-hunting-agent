from pathlib import Path
import pymupdf


PROFILE_DIR = Path("profile")
DEFAULT_RESUME_PDF = PROFILE_DIR / "resume.pdf"
DEFAULT_RESUME_TXT = PROFILE_DIR / "resume.txt"
DEFAULT_PREFERENCES = PROFILE_DIR / "preferences.txt"


def clean_extracted_text(text: str) -> str:
    """
    Basic cleanup for resume PDF extraction.
    Keeps it simple because the LLM can handle normal line breaks.
    """

    if not text:
        return ""

    lines = []

    for line in text.splitlines():
        line = line.strip()

        if not line:
            continue

        lines.append(line)

    return "\n".join(lines)


def extract_text_from_pdf(pdf_path: str | Path) -> str:
    """
    Extract text from a digitally-created PDF resume using PyMuPDF.
    This will work for most normal resume PDFs exported from Word, Google Docs, LaTeX, Canva, etc.
    """

    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"Resume PDF not found: {pdf_path}")

    doc = pymupdf.open(pdf_path)

    pages_text = []

    for page_index, page in enumerate(doc, start=1):
        text = page.get_text("text")

        if text and text.strip():
            pages_text.append(f"\n--- Page {page_index} ---\n{text}")

    raw_text = "\n".join(pages_text)
    cleaned = clean_extracted_text(raw_text)

    if len(cleaned.strip()) < 100:
        raise ValueError(
            "Extracted very little text from the resume PDF. "
            "This may be a image-based PDF which is not supported."
        )

    return cleaned


def load_resume_text() -> str:
    """
    Load resume from profile/resume.txt if it exists.
    Otherwise extract from profile/resume.pdf.
    """

    if DEFAULT_RESUME_TXT.exists():
        return DEFAULT_RESUME_TXT.read_text(encoding="utf-8").strip()

    if DEFAULT_RESUME_PDF.exists():
        extracted = extract_text_from_pdf(DEFAULT_RESUME_PDF)

        # Cache extracted text so the agent does not need to re-parse the PDF every run.
        DEFAULT_RESUME_TXT.write_text(extracted, encoding="utf-8")

        return extracted

    raise FileNotFoundError(
        "No resume found. Add either profile/resume.pdf or profile/resume.txt."
    )


def load_preferences_text() -> str:
    if not DEFAULT_PREFERENCES.exists():
        raise FileNotFoundError("Missing profile/preferences.txt")

    return DEFAULT_PREFERENCES.read_text(encoding="utf-8").strip()


def load_candidate_profile() -> dict:
    return {
        "resume_text": load_resume_text(),
        "preferences_text": load_preferences_text(),
    }

def refresh_resume_text_from_pdf() -> str:
    """
    Force re-extract profile/resume.pdf and overwrite profile/resume.txt.
    Use this after changing the resume PDF.
    """

    extracted = extract_text_from_pdf(DEFAULT_RESUME_PDF)
    DEFAULT_RESUME_TXT.write_text(extracted, encoding="utf-8")
    return extracted


if __name__ == "__main__":
    profile = load_candidate_profile()

    print("RESUME TEXT:")
    print(profile["resume_text"][:3000])

    print("\n\nPREFERENCES:")
    print(profile["preferences_text"])