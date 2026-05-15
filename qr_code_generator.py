import qrcode
import json

data = {
    "product": "coca_cola",
    "expiry": "2026-06-15",
    "id": "COLA002"
}

json_data = json.dumps(data)

qr = qrcode.QRCode(
    version=1,
    error_correction=qrcode.constants.ERROR_CORRECT_L,
    box_size=10,
    border=4,
)

qr.add_data(json_data)
qr.make(fit=True)

img = qr.make_image(fill_color="black", back_color="white")
img.save("qr_codes/coca_cola_qr_2.png")

print("QR saved as coca_cola_qr.png")