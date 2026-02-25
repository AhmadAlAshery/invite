from datetime import datetime, timedelta, timezone
from typing import Optional, Union
from jose import jwt  # type: ignore
from sqlalchemy.orm import load_only
from jose.exceptions import JWTError, ExpiredSignatureError  # type: ignore
import bcrypt
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from pydantic import SecretStr
from sqlalchemy import func
from src.core.config import settings
from PIL import Image, ImageDraw, ImageFont
import qrcode
from src.auth.model import Host, Guest
from src.auth.schema import HostCreate, HostResponse
from fastapi.responses import FileResponse
from pathlib import Path
import pandas as pd
import uuid
import zipfile
import os


import logging

logger = logging.getLogger(__name__)


def create_access_token(
    subject: Union[str, int], expires_delta: Optional[timedelta] = None
) -> str:
    """Create JWT access token using your settings"""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    # Store user ID as string in JWT
    to_encode = {"exp": expire, "sub": str(subject)}

    encoded_jwt = jwt.encode(
        to_encode, str(settings.SECRET_KEY), algorithm=settings.ALGORITHM
    )
    return encoded_jwt


def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password (str): The plaintext password

    Returns:
        str: The hashed password as a UTF-8 string
    """
    # bcrypt requires bytes, so encode first
    password_bytes = password.encode("utf-8")
    hashed_bytes = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    # return as string for storage (e.g., in DB)
    return hashed_bytes.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a stored bcrypt hash.

    Args:
        plain_password (str): The plaintext password to verify
        hashed_password (str): The stored hash (UTF-8 string)

    Returns:
        bool: True if password matches, False otherwise
    """
    # encode both to bytes
    plain_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(plain_bytes, hashed_bytes)


def decode_access_token(token: str) -> dict:
    """Decode JWT access token and return payload"""
    try:
        # Remove Bearer prefix if present
        if token.startswith("Bearer "):
            token = token[7:]

        payload = jwt.decode(
            token, str(settings.SECRET_KEY), algorithms=[settings.ALGORITHM]
        )
        return payload
    except ExpiredSignatureError:
        raise ValueError("Token has expired")
    except JWTError:
        raise ValueError("Invalid token")


class AuthService:
    """Service for handling user authentication and registration"""

    def login(self, db: Session, user_email: str, password: str):
        user = db.query(Host).filter(Host.email == user_email).first()

        if not user or not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user"
            )

        user.last_login = func.now()
        db.commit()

        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            subject=user.id, expires_delta=access_token_expires
        )

        return {
            "access_token": access_token,
            "token_type": "bearer",
        }

    def register(self, db: Session, user_data: HostCreate, full_url: str):
        try:
            # Check if user exists
            existing_user = db.query(Host).filter(Host.email == user_data.email).first()
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered",
                )
            password = user_data.password
            if isinstance(password, SecretStr):
                password = password.get_secret_value()
            hashed = get_password_hash(password)
            is_active = False
            if (
                user_data.email == "ahmedt_ash@yahoo.com"
                or user_data.email == "ahmedtash5@gmail.com"
                or user_data.email == "ahmed.ashkar@biotech-eg.com"
                or user_data.email == "ramy.elatwy@biotech-eg.com"
            ):
                is_active = True
            # Create user
            user = Host(
                email=user_data.email,
                hashed_password=hashed,
                first_name=getattr(user_data, "first_name", None),
                last_name=getattr(user_data, "last_name", None),
                is_active=is_active,
            )

            db.add(user)
            db.commit()
            db.refresh(user)

            return HostResponse.model_validate(user)

        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Registration failed: {type(e)} {str(e)}",
            )

    def get_all_hosts(self, db: Session, email: str):
        hosts = (
            db.query(Host)
            .options(
                load_only(
                    Host.email,
                    Host.first_name,
                    Host.last_name,
                    Host.is_active,
                )
            )
            .filter(Host.email != email)
            .all()
        )
        return hosts

    def activate_host(self, db: Session, user_email: str):
        try:
            user = db.query(Host).filter(Host.email == user_email).first()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Host with email {user_email} not found",
                )
            user.is_active = True
            db.commit()
            return {"message": f"Host with email {user_email} deleted successfully"}
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Deleting failed: {type(e)} {str(e)}",
            )

    def generate_images(self, db: Session, contents, invitation_name: str):
        base_path = Path("src") / "excel"
        base_path.mkdir(parents=True, exist_ok=True)

        images_path = Path("src") / "images"
        images_path.mkdir(parents=True, exist_ok=True)
        temp_path = Path("src") / "temp"
        temp_path.mkdir(parents=True, exist_ok=True)

        # Create unique filename
        file_id = uuid.uuid4().hex
        saved_path = base_path / f"{invitation_name}_{file_id}.xlsx"
        image_folder = images_path / file_id
        image_folder.mkdir(parents=True, exist_ok=True)

        # Save uploaded file temporarily
        try:
            # contents = file.read()
            with open(saved_path, "wb") as f:
                f.write(contents)
        except Exception:
            raise HTTPException(status_code=400, detail="Failed to save file")

        # Read with pandas
        try:
            df = pd.read_excel(saved_path)

            # Add column x (example: constant value)
            df["event_name"] = invitation_name
            df["event_id"] = file_id

            guests = []
            for _, row in df.iterrows():
                guest = Guest(
                    name=row["name"],
                    code=row["code"],
                    event_name=invitation_name,
                    event_id=file_id,
                )
                guests.append(guest)

            db.add_all(guests)
            db.flush()  # IDs generated here
            db.commit()

            df["id"] = [g.id for g in guests]

            # Save updated file
            df.to_excel(saved_path, index=False)

            for _, row in df.iterrows():
                data = f"{row['code']}-{row['name']}_{row['id']}"
                qr = qrcode.QRCode(
                    version=2,
                    error_correction=qrcode.constants.ERROR_CORRECT_M,  # pyright: ignore[reportAttributeAccessIssue]
                    box_size=10,
                    border=4,
                )
                qr.add_data(data)
                qr.make(fit=True)

                qr_image = qr.make_image(fill_color="black", back_color="white")
                qr_image_path = temp_path / f"{data}.png"
                qr_image.save(qr_image_path)  # pyright: ignore[reportArgumentType]
                background = Image.open("src/asset.jpeg")
                # Open the QR code image
                qr_image = Image.open(qr_image_path)

                # Optionally resize QR to fit nicely
                qr_image = qr_image.resize((240, 191))  # width, height in pixels

                position = (40, background.height - qr_image.height - 63)

                # Paste QR onto background
                background.paste(qr_image, position)

                # Save final image
                background.save(qr_image_path)

                add_name_to_invitation(
                    qr_image_path,
                    f"{row['code']}-{str(row['name'])[:20]}",
                    f"{image_folder/data}.png",
                )
                if qr_image_path.exists():
                    qr_image_path.unlink()

        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Excel processing failed: {str(e)}"
            )

        # Return modified
        # image_folder, saved_path
        # file_id name
        zip_file_name = base_path / (f"{invitation_name}_{file_id}.zip")
        zip_file_and_folder(zip_file_name, saved_path, image_folder)
        if saved_path.exists():
            saved_path.unlink()
        # return FileResponse(
        #     path=zip_file_name,
        #     filename=zip_file_name.name,
        #     # media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        #     media_type="application/zip",
        # )
        return zip_file_name


def add_name_to_invitation(input, name, output):
    """Add a name to the invitation with gold color matching the theme"""
    name = name[:20]
    # Load the image
    img = Image.open(input)
    draw = ImageDraw.Draw(img)

    # Define the white box area (bottom left)
    box_x = 40
    box_y = 1075
    box_width = 240
    box_height = 105

    font_color = (7, 7, 7)

    # Try to find the best bold font
    font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    best_font = ImageFont.truetype(font_path, 30)  # safe fallback
    try:
        # Try different sizes from large to small
        for size in range(30, 18, -1):
            try:
                font = ImageFont.truetype(font_path, size)
                bbox = draw.textbbox((0, 0), name, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]

                # Check if it fits with padding
                if text_width <= (box_width - 20) and text_height <= (box_height - 20):
                    best_font = font
                    break
            except Exception:
                continue
    except Exception as e:
        print(e)

    # Calculate centered position
    bbox = draw.textbbox((0, 0), name, font=best_font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = box_x + (box_width - text_width) // 2
    y = box_y + (box_height - text_height) // 2

    # Draw the text in gold
    draw.text((x, y), name, font=best_font, fill=font_color)

    # Save to outputs
    img.save(output)

    return True


async def check_in_by_qr_code(db: Session, code):
    try:
        id = code.split("_")[-1]
        guest = db.query(Guest).filter(Guest.id == id).first()
        if not guest:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Guest not found in the Database.",
            )
        if not guest.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Guest is not active.",
            )
        if guest.checked_in:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Guest has already checked in before.",
            )
        guest.checked_in = True
        db.commit()
        return True

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"check_in_by_qr_code failed: {type(e)} {str(e)}",
        )


def zip_file_and_folder(zip_name, file_path, folder_path):
    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as z:
        # Add single file
        z.write(file_path, arcname=os.path.basename(file_path))

        # Add folder recursively
        for root, _, files in os.walk(folder_path):
            for file in files:
                full_path = os.path.join(root, file)
                arcname = os.path.relpath(full_path, start=os.path.dirname(folder_path))
                z.write(full_path, arcname)
