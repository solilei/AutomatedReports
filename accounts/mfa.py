import pyotp
import segno

ISSUER = "Cadet Soft Skills"


def new_secret():
    return pyotp.random_base32()


def provisioning_uri(secret, username):
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=ISSUER)


def qr_svg(uri):
    return segno.make(uri).svg_inline(scale=4)


def verify(secret, code):
    return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)
