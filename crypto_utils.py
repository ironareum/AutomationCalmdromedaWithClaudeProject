"""
파일 암호화/복호화 유틸리티
2026.03.29 used_assets.json, history.txt 암호화 → GitHub 리포 안전 저장

[암호화 방식]
- AES-256-GCM (Fernet 기반) — 표준 대칭키 암호화
- 키: 환경변수 ENCRYPTION_KEY (base64 인코딩된 32바이트)

[사용법]
  # 키 최초 생성 (로컬에서 한 번만 실행)
  python crypto_utils.py --generate-key

  # 암호화 (평문 → .enc)
  python crypto_utils.py --encrypt used_assets.json
  python crypto_utils.py --encrypt history.txt

  # 복호화 (.enc → 평문)
  python crypto_utils.py --decrypt used_assets.enc
  python crypto_utils.py --decrypt history.enc

[GitHub Secrets 설정]
  ENCRYPTION_KEY = (--generate-key로 출력된 값)
"""

import argparse
import base64
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()


def _get_key() -> bytes:
    """환경변수 ENCRYPTION_KEY에서 키 로드"""
    raw = os.environ.get("ENCRYPTION_KEY", "")
    if not raw:
        raise ValueError(
            "ENCRYPTION_KEY 환경변수가 없습니다.\n"
            "python crypto_utils.py --generate-key 로 키를 생성하세요."
        )
    return base64.urlsafe_b64decode(raw.encode())


def generate_key() -> str:
    """32바이트 랜덤 키 생성 후 base64 인코딩 반환"""
    key_bytes = os.urandom(32)
    return base64.urlsafe_b64encode(key_bytes).decode()


def encrypt_file(input_path: Path, output_path: Path | None = None) -> Path:
    """
    파일 암호화 → .enc 파일 저장
    AES-256-GCM: nonce(12) + ciphertext + tag(16)
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key   = _get_key()
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)

    plaintext = input_path.read_bytes()
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    # 출력 경로: 지정 없으면 .enc 확장자 추가
    out = output_path or input_path.with_suffix(input_path.suffix + ".enc")
    out.write_bytes(nonce + ciphertext)
    print(f"암호화 완료: {input_path.name} → {out.name}")
    return out


def decrypt_file(input_path: Path, output_path: Path | None = None) -> Path:
    """
    .enc 파일 복호화 → 원본 파일 복원
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key    = _get_key()
    aesgcm = AESGCM(key)

    data      = input_path.read_bytes()
    nonce     = data[:12]
    ciphertext = data[12:]

    plaintext = aesgcm.decrypt(nonce, ciphertext, None)

    # 출력 경로: 지정 없으면 .enc 제거
    if output_path:
        out = output_path
    elif input_path.suffix == ".enc":
        out = input_path.with_suffix("")  # history.txt.enc → history.txt
    else:
        out = input_path.parent / (input_path.stem + "_decrypted" + input_path.suffix)

    out.write_bytes(plaintext)
    print(f"복호화 완료: {input_path.name} → {out.name}")
    return out


# ── CLI ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="파일 암호화/복호화 유틸리티")
    group  = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate-key", action="store_true",
                       help="새 암호화 키 생성 (GitHub Secrets에 등록)")
    group.add_argument("--encrypt", metavar="FILE",
                       help="파일 암호화 → .enc 생성")
    group.add_argument("--decrypt", metavar="FILE",
                       help=".enc 파일 복호화 → 원본 복원")
    args = parser.parse_args()

    if args.generate_key:
        key = generate_key()
        print(f"\n생성된 키 (GitHub Secrets → ENCRYPTION_KEY 에 등록):\n{key}\n")
        print("⚠️  이 키를 잃어버리면 암호화된 파일을 복구할 수 없습니다. 안전한 곳에 백업하세요.")

    elif args.encrypt:
        path = Path(args.encrypt)
        if not path.exists():
            print(f"파일 없음: {path}")
            sys.exit(1)
        encrypt_file(path)

    elif args.decrypt:
        path = Path(args.decrypt)
        if not path.exists():
            print(f"파일 없음: {path}")
            sys.exit(1)
        decrypt_file(path)