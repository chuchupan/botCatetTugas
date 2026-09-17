import os
import google.generativeai as genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

MODEL_NAME = "gemini-3.6-flash"

PROMPT = """Kamu membantu mahasiswa mencatat tugas kuliah dari foto.
Lihat gambar ini (bisa berupa soal tugas, slide, papan tulis, atau screenshot).
Jawab SINGKAT dalam Bahasa Indonesia dengan format persis seperti ini:

Mata kuliah: <tebakan mata kuliah, atau "tidak diketahui" kalau tidak jelas>
Ringkasan: <ringkasan singkat 1-2 kalimat tentang isi tugas/soal ini>

Jangan tambahkan teks lain di luar format itu."""


def analyze_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Kirim gambar ke Gemini dan kembalikan hasil analisis singkat dalam teks."""
    try:
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content(
            [
                {"mime_type": mime_type, "data": image_bytes},
                PROMPT,
            ]
        )
        return response.text.strip()
    except Exception as e:
        return f"(Gagal menganalisis foto otomatis: {e})"
        
