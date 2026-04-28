# AI Schemas (MVP)

Folder ini berisi draft JSON Schema untuk pipeline `AI Site Copilot`.

## Daftar Schema
- `template.schema.json`
  - Output untuk pembuatan template baru (`Template Builder Copilot`).
- `site-content.schema.json`
  - Output untuk pembuatan konten website berdasarkan template (`Website Content Copilot`).
- `fe-guide.schema.json`
  - Output metadata + markdown guide FE untuk mode template.
- `copilot-message.schema.json`
  - Struktur pesan chat Copilot, termasuk attachment gambar (MVP included).

## Catatan MVP (Image Included)
- Attachment gambar didukung dari awal melalui `attachments[]`.
- Backend tetap perlu melakukan:
  - upload image ke storage internal dulu
  - pass URL final ke LLM
  - validasi ukuran/tipe file sebelum dipakai model

## Rekomendasi Validasi Runtime
- Jalankan validasi schema pada setiap draft sebelum status `ready_for_publish`.
- Jika invalid, simpan `validation_report` dan lakukan auto-repair pass.
- Tetapkan hard limits jumlah page/section/block/item untuk mencegah output terlalu besar.
