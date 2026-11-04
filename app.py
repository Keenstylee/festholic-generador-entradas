from __future__ import annotations

import hashlib
from datetime import datetime
from io import BytesIO
import json
from pathlib import Path
import re
import secrets
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid
import zipfile
from zoneinfo import ZoneInfo

import cv2
import numpy as np
import streamlit as st

from src.pdf_editor import detect_ticket_template, edit_ticket_fields, inspect_pdf, inspect_ticket_fields
from src.pdf_preview import pdf_page_count as count_pdf_pages
from src.pdf_preview import render_pdf_page as render_page_png
from src.pipeline import process_image
from src.reconstruction import encode_png


APP_DIR = Path(__file__).resolve().parent
DEFAULT_TEMPLATE_PATHS = {
    "Plantilla Teleticket": APP_DIR / "assets" / "plantilla-teleticket.pdf",
    "Plantilla Ticketmaster": APP_DIR / "assets" / "plantilla-ticketmaster.pdf",
    "Plantilla Joinnus": APP_DIR / "assets" / "plantilla-joinnus.pdf",
}
DEFAULT_JOINNUS_EVENT_IMAGE_PATH = APP_DIR / "assets" / "sound-music-festival-2026.jpg"
JOINNUS_SOUND_MUSIC_DEFAULTS = {
    "event": "SOUND MUSIC FESTIVAL 2026",
    "day": "Sábado",
    "date": "07 de noviembre, 2026",
    "time": "03:00 PM",
    "location": "ESTADIO NACIONAL",
    "address": "CL. JOSÉ DÍAZ S/N, CERCADO DE LIMA, LIMA",
    "ticket_type": "OCCIDENTE",
    "category": "CORTESÍA",
    "price": "S/ 0.00",
    "row": "",
    "seat": "",
    "producer": "",
    "ruc": "",
    "attendee_name": "PROHIBIDA SU VENTA",
    "attendee_dni": "00000000",
}
FESTHOLIC_GENERATION_ENDPOINT = "https://festholic.com/api/digitalizer/generation"
MAX_SEAT_TICKETS = 60

st.set_page_config(page_title="Digitalizador de entradas | Festholic", page_icon="🎟️", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;600;700&display=swap');
    :root{--fh-bg:#242426;--fh-deep:#0f1015;--fh-panel:#15161b;--fh-card:#1b1b22;--fh-card-deep:#121319;--fh-input:#181920;--fh-text:#fff;--fh-muted:#bbb6c2;--fh-faint:#918d99;--fh-border:rgba(255,255,255,.10);--fh-pink:#ff2e9f;--fh-orange:#ff7043;--fh-cyan:#25c9e8;--fh-green:#51d98a}
    html,body,[data-testid="stAppViewContainer"],.stApp{background:var(--fh-bg);color:var(--fh-text);font-family:"Manrope",system-ui,sans-serif}
    [data-testid="stAppViewContainer"]{position:relative;isolation:isolate;background:radial-gradient(circle at 108% 4%,rgba(37,201,232,.075) 0 110px,transparent 111px),radial-gradient(circle at -8% 88%,rgba(255,46,159,.045) 0 150px,transparent 151px),var(--fh-bg)}
    [data-testid="stAppViewContainer"]::before{content:"";position:fixed;z-index:0;right:-170px;top:24%;width:360px;height:360px;border:46px solid rgba(37,201,232,.035);border-radius:50%;pointer-events:none}
    [data-testid="stHeader"],#MainMenu,footer{display:none!important}
    [data-testid="stMainBlockContainer"]{position:relative;z-index:1;width:100%;max-width:1440px;padding:18px 18px 44px}
    h1,h2,h3,[data-testid="stHeading"]{font-family:"Space Grotesk","Manrope",sans-serif;letter-spacing:-.03em}
    p,label,[data-testid="stCaptionContainer"]{color:var(--fh-muted)}
    .tool-identity{display:flex;align-items:center;gap:13px;min-width:0;padding:10px 0 14px}
    .tool-icon{width:34px;height:42px;flex:0 0 auto;display:grid;place-items:center;color:var(--fh-cyan);background:transparent}
    .tool-icon svg{width:26px;height:26px}.tool-identity h1{margin:0;color:#fff;font-size:clamp(28px,3vw,34px);font-weight:800;line-height:1.05}.tool-identity p{margin:7px 0 0;color:var(--fh-muted);font-size:12px;line-height:1.5}
    .section-intro{position:relative;margin:2px 0 15px;padding-left:0}.section-intro strong{display:block;color:#f8f8fb;font-family:"Space Grotesk","Manrope",sans-serif;font-size:16px;font-weight:750;letter-spacing:-.02em}.section-intro span{display:block;margin-top:4px;color:var(--fh-muted);font-size:10.5px;line-height:1.45}
    .section-intro--accent{padding-left:13px;margin-top:4px;margin-bottom:17px}.section-intro--accent::before{content:"";position:absolute;left:0;top:2px;bottom:2px;width:3px;border-radius:3px}.section-intro--pink::before{background:var(--fh-pink);box-shadow:0 0 12px rgba(255,46,159,.20)}.section-intro--cyan::before{background:var(--fh-cyan);box-shadow:0 0 12px rgba(37,201,232,.18)}.section-intro--orange::before{background:var(--fh-orange);box-shadow:0 0 12px rgba(255,112,67,.18)}
    .section-intro--step{display:grid;grid-template-columns:32px minmax(0,1fr);align-items:center;gap:10px;padding-left:0!important}.section-intro--step::before{display:none}.section-intro__number{width:32px;height:32px;display:grid!important;place-items:center;margin:0!important;border:1px solid rgba(37,201,232,.34);border-radius:50%;color:var(--fh-cyan)!important;background:rgba(37,201,232,.11);box-shadow:inset 0 1px 0 rgba(255,255,255,.06);font-size:12px!important;font-weight:900;line-height:1!important}.section-intro--pink .section-intro__number{border-color:rgba(255,46,159,.36);color:#ff70b9!important;background:rgba(255,46,159,.12)}.section-intro--orange .section-intro__number{border-color:rgba(255,112,67,.38);color:#ff9a78!important;background:rgba(255,112,67,.12)}.section-intro__copy{min-width:0}.section-intro__copy span{margin-top:3px}
    .preview-marker,.card-accent,.image-upload-marker{height:0;overflow:hidden}
    [data-testid="stVerticalBlockBorderWrapper"]{position:relative;overflow:hidden;border:1px solid var(--fh-border)!important;border-radius:18px!important;background:radial-gradient(circle at 94% 5%,rgba(37,201,232,.045),transparent 8rem),linear-gradient(135deg,var(--fh-card),var(--fh-card-deep))!important;box-shadow:0 16px 34px rgba(0,0,0,.22),inset 0 1px 0 rgba(255,255,255,.035)}
    [data-testid="stVerticalBlockBorderWrapper"]:has(.card-accent)::before{content:"";position:absolute;z-index:2;left:0;top:20%;width:3px;height:60%;border-radius:0 3px 3px 0}.st-key-pdf_card::before,[data-testid="stVerticalBlockBorderWrapper"]:has(.card-accent--pdf)::before{background:var(--fh-pink);box-shadow:0 0 13px rgba(255,46,159,.22)}.st-key-qr_card::before,[data-testid="stVerticalBlockBorderWrapper"]:has(.card-accent--qr)::before{background:var(--fh-cyan);box-shadow:0 0 13px rgba(37,201,232,.20)}.st-key-preview_card::before,[data-testid="stVerticalBlockBorderWrapper"]:has(.card-accent--preview)::before{background:var(--fh-orange);box-shadow:0 0 13px rgba(255,112,67,.20)}
    [data-testid="stHorizontalBlock"]:has(.st-key-pdf_card):has(.st-key-qr_card){align-items:stretch!important}[data-testid="stHorizontalBlock"]:has(.st-key-pdf_card):has(.st-key-qr_card)>[data-testid="stColumn"]{display:flex!important;align-self:stretch!important}[data-testid="stHorizontalBlock"]:has(.st-key-pdf_card):has(.st-key-qr_card)>[data-testid="stColumn"]>div{width:100%;height:100%}.st-key-pdf_card,.st-key-qr_card{width:100%;height:100%;min-height:250px;box-sizing:border-box}.st-key-pdf_card>[data-testid="stVerticalBlock"],.st-key-qr_card>[data-testid="stVerticalBlock"]{height:100%;display:flex;flex-direction:column}.st-key-pdf_ready,.st-key-pdf_upload,.st-key-qr_upload{margin-top:auto;margin-bottom:4px}
    [data-testid="stVerticalBlockBorderWrapper"]:has(.tool-identity){position:relative;overflow:visible;border:0!important;border-radius:0!important;background:transparent!important;box-shadow:none!important}
    [data-testid="stVerticalBlockBorderWrapper"]:has(.tool-identity)::after{content:"";position:absolute;left:0;bottom:2px;width:156px;height:2px;border-radius:2px;background:linear-gradient(90deg,#ff2e9f 0 38%,#ff7043 38% 68%,#25c9e8 68% 100%);opacity:.9}
    [data-testid="stVerticalBlockBorderWrapper"]:has(.preview-marker){position:sticky;top:16px;background:radial-gradient(circle at 94% 5%,rgba(255,112,67,.055),transparent 9rem),linear-gradient(145deg,#18191f,#101116)!important}
    [data-testid="stFileUploaderDropzone"]{min-height:100px;padding:12px 16px!important;border:1px dashed rgba(37,201,232,.35)!important;border-radius:14px!important;background:rgba(37,201,232,.045)!important;display:flex!important;flex-direction:column!important;align-items:center!important;justify-content:center!important;gap:6px!important;text-align:center!important;transition:border-color .16s ease,background .16s ease,transform .16s ease}
    [data-testid="stFileUploaderDropzone"]::before{content:"Arrastra tu archivo aquí o selecciónalo";color:#fff;font-size:10.5px;font-weight:750}.st-key-pdf_upload [data-testid="stFileUploaderDropzone"]::before{content:"Arrastra tu PDF aquí o selecciónalo"}.st-key-qr_upload [data-testid="stFileUploaderDropzone"]::before{content:"Arrastra una imagen aquí o selecciónala"}.st-key-event_image_upload [data-testid="stFileUploaderDropzone"]::before{content:"Sube una nueva imagen del evento"}
    [data-testid="stFileUploaderDropzone"]:hover{border-color:rgba(37,201,232,.62)!important;background:rgba(37,201,232,.075)!important;transform:translateY(-1px)}
    [data-testid="stFileUploaderDropzone"] svg{width:30px!important;height:30px!important;color:var(--fh-cyan)!important;fill:var(--fh-cyan)!important}[data-testid="stFileUploaderDropzoneInstructions"]{text-align:center!important}[data-testid="stFileUploaderDropzoneInstructions"] span{color:#fff!important;font-weight:750!important}[data-testid="stFileUploaderDropzoneInstructions"] small{display:block!important;margin-top:3px!important;color:var(--fh-muted)!important;white-space:normal!important}
    [data-testid="stFileUploaderDropzone"] button{min-width:168px!important;min-height:40px!important;border-color:rgba(37,201,232,.30)!important;background:rgba(37,201,232,.14)!important;color:var(--fh-cyan)!important;font-size:0!important}[data-testid="stFileUploaderDropzone"] button>*{display:none!important}[data-testid="stFileUploaderDropzone"] button::after{content:"Seleccionar archivo";display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:800}
    [data-testid="stVerticalBlockBorderWrapper"]:has(.card-accent--pdf) [data-testid="stFileUploaderDropzone"] button::after{content:"Seleccionar PDF"}[data-testid="stVerticalBlockBorderWrapper"]:has(.card-accent--qr) [data-testid="stFileUploaderDropzone"] button::after{content:"Cargar fotografía"}
    .st-key-event_image_upload [data-testid="stFileUploaderDropzone"]{border-color:rgba(255,112,67,.34)!important;background:rgba(255,112,67,.045)!important}.st-key-event_image_upload [data-testid="stFileUploaderDropzone"]:hover{border-color:rgba(255,112,67,.60)!important;background:rgba(255,112,67,.075)!important}.st-key-event_image_upload [data-testid="stFileUploaderDropzone"] svg{color:var(--fh-orange)!important;fill:var(--fh-orange)!important}.st-key-event_image_upload [data-testid="stFileUploaderDropzone"] button{border-color:rgba(255,112,67,.30)!important;background:rgba(255,112,67,.14)!important;color:var(--fh-orange)!important}.st-key-event_image_upload [data-testid="stFileUploaderDropzone"] button::after{content:"Cambiar imagen"}
    [data-testid="stFileUploaderFile"]{border:1px solid var(--fh-border);border-radius:12px;background:rgba(255,255,255,.025)}
    .template-ready-zone{min-height:100px;display:flex;align-items:center;gap:12px;padding:4px 8px;border:0;background:transparent;color:#dffbec;font-size:13px;font-weight:700}.template-ready-zone__icon{width:30px;height:30px;flex:0 0 auto;display:grid;place-items:center;border-radius:9px;background:rgba(81,217,138,.16);color:var(--fh-green);font-size:18px}.template-ready-zone small{display:block;margin-top:4px;color:rgba(223,251,236,.64);font-size:10px;font-weight:600}
    .qr-process{position:relative;overflow:hidden;padding:15px;border:1px solid rgba(81,217,138,.25);border-radius:16px;background:radial-gradient(circle at 100% 0,rgba(81,217,138,.11),transparent 8rem),linear-gradient(145deg,#171d1a,#101413);box-shadow:inset 0 1px 0 rgba(255,255,255,.04),0 12px 24px rgba(0,0,0,.16)}
    .qr-process__head{display:grid;grid-template-columns:36px minmax(0,1fr) auto;align-items:center;gap:10px}.qr-process__icon{width:36px;height:36px;display:grid;place-items:center;border-radius:11px;background:rgba(81,217,138,.14);color:var(--fh-green)}.qr-process__icon svg{width:20px;height:20px}.qr-process__head strong{display:block;color:#fff;font-family:"Space Grotesk","Manrope",sans-serif;font-size:13px;line-height:1.2}.qr-process__head small{display:block;margin-top:3px;color:#9fb2a8;font-size:9px;line-height:1.35}.qr-process__count{color:var(--fh-green);font-size:11px;font-weight:850}
    .qr-process__bar{height:3px;margin:13px 0 14px;border-radius:3px;background:rgba(255,255,255,.07);overflow:hidden}.qr-process__bar span{display:block;width:100%;height:100%;border-radius:inherit;background:linear-gradient(90deg,rgba(81,217,138,.55),var(--fh-green))}
    .qr-process__steps{display:grid;gap:9px}.qr-process__step{position:relative;display:grid;grid-template-columns:24px minmax(0,1fr);align-items:start;gap:9px}.qr-process__step:not(:last-child)::after{content:"";position:absolute;left:11px;top:23px;width:1px;height:calc(100% + 8px);background:rgba(81,217,138,.24)}.qr-process__step>span{position:relative;z-index:1;width:24px;height:24px;display:grid;place-items:center;border:1px solid rgba(81,217,138,.35);border-radius:50%;background:#17241d;color:var(--fh-green);font-size:11px;font-weight:900}.qr-process__step b{display:block;padding-top:1px;color:#edf7f1;font-size:10.5px;line-height:1.25}.qr-process__step small{display:block;margin-top:2px;color:#8fa097;font-size:8.5px;line-height:1.3}.qr-process__approved{display:flex;align-items:center;gap:7px;margin-top:13px;padding-top:11px;border-top:1px solid rgba(255,255,255,.07);color:var(--fh-green);font-size:9px;font-weight:800;letter-spacing:.02em}.qr-process__approved svg{width:14px;height:14px;flex:0 0 auto}
    [data-baseweb="input"]>div,[data-baseweb="select"]>div{min-height:42px;border-color:rgba(255,255,255,.09)!important;border-radius:11px!important;background:var(--fh-input)!important}
    [data-baseweb="input"]>div:focus-within,[data-baseweb="select"]>div:focus-within{border-color:rgba(37,201,232,.55)!important;box-shadow:0 0 0 3px rgba(37,201,232,.10)!important}
    [role="radiogroup"] label:has(input:checked){color:var(--fh-cyan)!important}
    [data-testid="stWidgetLabel"] p{color:#ddd9e2;font-size:10px;font-weight:750}[data-testid="stImage"] img{border:1px solid rgba(255,255,255,.10);border-radius:14px}[data-testid="stAlert"]{border:1px solid var(--fh-border);border-radius:14px;background:rgba(18,19,25,.88)!important}hr{border-color:rgba(255,255,255,.065)!important;margin:20px 0!important}
    .stButton>button,.stDownloadButton>button{min-height:42px;border-radius:13px!important;font-weight:800!important}.stButton>button[kind="secondary"]{border-color:var(--fh-border);color:#ececf2;background:#17181e}
    .stButton>button[kind="secondary"]:hover{border-color:rgba(37,201,232,.28);color:var(--fh-cyan);background:rgba(37,201,232,.10)}
    .stDownloadButton>button[kind="primary"]{min-height:54px;border:0!important;background:#ff2e9f!important;color:#fff!important;box-shadow:0 10px 24px rgba(255,46,159,.23),inset 0 1px 0 rgba(255,255,255,.18)}
    .stDownloadButton>button[kind="primary"] *,.stDownloadButton>button[kind="primary"] p{color:#fff!important;opacity:1!important}.stDownloadButton>button[kind="primary"]:hover{filter:brightness(1.08);transform:translateY(-1px)}.stButton>button:disabled{opacity:1!important;border-color:rgba(255,255,255,.06)!important;background:#2a2b31!important;color:#777b84!important}
    .stButton>button[kind="primary"]{min-height:50px;border:0!important;background:#ff2e9f!important;color:#fff!important;box-shadow:0 10px 24px rgba(255,46,159,.22),inset 0 1px 0 rgba(255,255,255,.18)}.stButton>button[kind="primary"] *,.stButton>button[kind="primary"] p{color:#fff!important}.stButton>button[kind="primary"]:hover{filter:brightness(1.08);transform:translateY(-1px)}
    .batch-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:2px 0 14px}.batch-summary__item{padding:11px 12px;border:1px solid rgba(255,255,255,.08);border-radius:12px;background:#181920}.batch-summary__item strong{display:block;color:#fff;font-family:"Space Grotesk","Manrope",sans-serif;font-size:17px}.batch-summary__item span{display:block;margin-top:2px;color:var(--fh-muted);font-size:9px}.batch-summary__item--ok strong{color:var(--fh-green)}.batch-summary__item--error strong{color:var(--fh-orange)}
    [data-testid="stDialog"]:has(.completion-modal) [role="dialog"]{border:1px solid rgba(255,255,255,.11);border-radius:20px;background:radial-gradient(circle at 100% 0,rgba(37,201,232,.08),transparent 15rem),linear-gradient(145deg,#1b1b22,#101116);box-shadow:0 30px 80px rgba(0,0,0,.48)}
    .completion-modal{position:relative;margin:-4px 0 2px;padding:4px 0 12px}.completion-modal::after{content:"";display:block;width:138px;height:2px;margin-top:14px;border-radius:2px;background:linear-gradient(90deg,#ff2e9f 0 38%,#ff7043 38% 68%,#25c9e8 68% 100%)}.completion-modal__eyebrow{color:var(--fh-cyan);font-size:9px;font-weight:900;letter-spacing:.16em;text-transform:uppercase}.completion-modal__title{margin:6px 0 5px;color:#fff;font-family:"Space Grotesk","Manrope",sans-serif;font-size:22px;font-weight:800;letter-spacing:-.035em}.completion-modal__copy{margin:0;color:var(--fh-muted);font-size:11px;line-height:1.5}
    .completion-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:4px 0 12px}.completion-stat{padding:11px 12px;border:1px solid rgba(255,255,255,.08);border-radius:12px;background:#17181e}.completion-stat strong{display:block;color:#fff;font-family:"Space Grotesk","Manrope",sans-serif;font-size:19px}.completion-stat span{display:block;margin-top:2px;color:var(--fh-muted);font-size:9px}.completion-stat--ok strong{color:var(--fh-green)}.completion-stat--warn strong{color:var(--fh-orange)}
    .support-card{position:relative;overflow:hidden;margin-top:14px;padding:14px 15px 14px 18px;border:1px solid rgba(255,112,67,.20);border-radius:15px;background:radial-gradient(circle at 100% 0,rgba(255,112,67,.10),transparent 9rem),#171719}.support-card::before{content:"";position:absolute;left:0;top:17%;bottom:17%;width:3px;border-radius:0 3px 3px 0;background:var(--fh-orange)}.support-card__label{color:#ff9b79;font-size:9px;font-weight:900;letter-spacing:.12em;text-transform:uppercase}.support-card strong{display:block;margin-top:5px;color:#fff;font-family:"Space Grotesk","Manrope",sans-serif;font-size:14px}.support-card p{margin:4px 0 10px;color:var(--fh-muted);font-size:10px;line-height:1.45}.support-card__account{display:flex;flex-wrap:wrap;gap:6px 13px;color:#fff;font-size:11px;font-weight:800}.support-card__account span:first-child{color:var(--fh-cyan)}
    @media(max-width:900px){[data-testid="stMainBlockContainer"]{padding:12px 11px 36px}[data-testid="stHorizontalBlock"]{flex-wrap:wrap}[data-testid="stHorizontalBlock"]>[data-testid="stColumn"]{min-width:100%!important;width:100%!important}[data-testid="stVerticalBlockBorderWrapper"]:has(.preview-marker){position:static}.tool-identity{padding-top:4px}.tool-identity h1{font-size:28px}.batch-summary{grid-template-columns:1fr}}
    .seat-summary{margin:0 0 10px;padding:10px 12px;border:1px solid rgba(255,255,255,.08);border-radius:12px;background:#181920}.seat-summary__top{display:flex;align-items:baseline;justify-content:space-between;gap:10px;color:var(--fh-muted);font-size:10.5px}.seat-summary__top b{color:#fff;font-family:"Space Grotesk","Manrope",sans-serif;font-size:15px}.seat-summary__ok{color:var(--fh-green)}.seat-summary__bad{color:var(--fh-orange)}.seat-summary__bar{height:3px;margin-top:8px;border-radius:3px;background:rgba(255,255,255,.07);overflow:hidden}.seat-summary__bar span{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,rgba(81,217,138,.55),var(--fh-green))}
    .st-key-seat_slots [class*="st-key-seat_slot_"]{padding:8px 9px 6px;border:1px solid rgba(255,255,255,.08);border-radius:12px;background:#15161c;gap:.25rem}
    .st-key-seat_slots [data-testid="stVerticalBlock"]{gap:.5rem}
    .seat-badge{display:grid;place-items:center;width:30px;height:30px;border-radius:9px;background:rgba(37,201,232,.12);color:var(--fh-cyan);font-size:11px;font-weight:850}.seat-badge--ok{background:rgba(81,217,138,.18);color:var(--fh-green)}.seat-badge--bad{background:rgba(255,112,67,.18);color:var(--fh-orange)}
    .seat-note{margin:0 0 0 2px;color:var(--fh-orange);font-size:10px;line-height:1.35}
    .st-key-seat_slots [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:6px!important;align-items:center!important}
    .st-key-seat_slots [data-testid="stHorizontalBlock"]>[data-testid="stColumn"]{min-width:0!important}
    .st-key-seat_slots [data-testid="stHorizontalBlock"]>[data-testid="stColumn"]:nth-child(1){flex:0 0 32px!important;width:32px!important}
    .st-key-seat_slots [data-testid="stHorizontalBlock"]>[data-testid="stColumn"]:nth-child(2){flex:1 1 0!important;width:auto!important}
    .st-key-seat_slots [data-testid="stHorizontalBlock"]>[data-testid="stColumn"]:nth-child(3),.st-key-seat_slots [data-testid="stHorizontalBlock"]>[data-testid="stColumn"]:nth-child(4){flex:0 0 21%!important;width:21%!important}
    .st-key-seat_slots [data-testid="stFileUploaderDropzone"]{min-height:0!important;padding:3px 6px!important;flex-direction:row!important;gap:6px!important;border-radius:10px!important}.st-key-seat_slots [data-testid="stFileUploaderDropzone"]::before{display:none!important}.st-key-seat_slots [data-testid="stFileUploaderDropzoneInstructions"]{display:none!important}.st-key-seat_slots [data-testid="stFileUploaderDropzone"] svg{display:none!important}
    .st-key-seat_slots [data-testid="stFileUploaderDropzone"] button{min-width:0!important;width:100%!important;min-height:34px!important}.st-key-seat_slots [data-testid="stFileUploaderDropzone"] button::after{content:"Subir QR"!important}
    [data-testid="stFileChipDeleteBtn"] button{min-width:30px!important;width:30px!important;min-height:30px!important;padding:0!important;display:inline-flex!important;align-items:center;justify-content:center}[data-testid="stFileChipDeleteBtn"] button::after{content:"✕"!important;font-size:12px!important}
    .st-key-seat_slots [data-testid="stFileChipDeleteBtn"] button{width:30px!important;min-width:30px!important;min-height:30px!important}.st-key-seat_slots [data-testid="stFileChipDeleteBtn"] button::after{content:"✕"!important;font-size:12px!important}
    .st-key-seat_slots [data-testid="stFileChips"]{width:100%}.st-key-seat_slots [data-testid="stFileChip"]{width:100%;min-height:34px;padding:0 2px 0 6px!important;background:transparent!important;color:#fff!important;justify-content:space-between}.st-key-seat_slots [data-testid="stFileChip"]>div:first-child{display:none!important}.st-key-seat_slots [data-testid="stFileChipName"]{color:#fff!important;font-size:11px!important;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.st-key-seat_slots [data-testid="stFileChipName"]+div{display:none!important}.st-key-seat_slots [data-testid="stBaseButton-borderlessIcon"]{display:none!important}
    .st-key-seat_slots [data-baseweb="input"]>div{min-height:36px!important;border-radius:9px!important}.st-key-seat_slots input{padding:0 8px!important;font-size:12.5px!important;text-align:center}
    .qr-process__more{margin-top:10px}.qr-process__more summary{cursor:pointer;color:#9fb2a8;font-size:10px;font-weight:750;list-style:none}.qr-process__more summary::-webkit-details-marker{display:none}.qr-process__more summary::before{content:"▸ "}.qr-process__more[open] summary::before{content:"▾ "}.qr-process__more .qr-process__steps{margin-top:10px}
    .st-key-qr_result_card [data-testid="stImage"] img{max-height:240px;object-fit:contain}
    @media(max-width:900px){.st-key-qr_result_card [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important;gap:6px!important}.st-key-qr_result_card [data-testid="stHorizontalBlock"]>[data-testid="stColumn"]{min-width:0!important}.st-key-qr_result_card [data-testid="stHorizontalBlock"]>[data-testid="stColumn"]:nth-child(1),.st-key-qr_result_card [data-testid="stHorizontalBlock"]>[data-testid="stColumn"]:nth-child(3){flex:0 0 calc(44% - 4px)!important;width:calc(44% - 4px)!important}.st-key-qr_result_card [data-testid="stHorizontalBlock"]>[data-testid="stColumn"]:nth-child(2){flex:0 0 8%!important;width:8%!important}.st-key-qr_result_card [data-testid="stHorizontalBlock"]>[data-testid="stColumn"]:nth-child(4){flex:0 0 100%!important;width:100%!important}.qr-process{padding:12px}.st-key-qr_result_card [data-testid="stImage"] img{max-height:170px}}
    @media(max-width:900px){.batch-summary{grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:6px}.batch-summary__item{padding:8px 9px}.batch-summary__item strong{font-size:15px}.batch-summary__item span{font-size:8.5px}.st-key-seat_slots [data-testid="stHorizontalBlock"]>[data-testid="stColumn"]:nth-child(3),.st-key-seat_slots [data-testid="stHorizontalBlock"]>[data-testid="stColumn"]:nth-child(4){flex:0 0 22%!important;width:22%!important}.completion-stats{grid-template-columns:repeat(3,minmax(0,1fr));gap:6px}.completion-stat{padding:9px}.support-card__account{display:grid;gap:4px}}

    /* Festholic App UI — interfaz sobria, táctil y centrada en la tarea */
    :root{--fh-bg:#09090b;--fh-deep:#09090b;--fh-panel:#101014;--fh-card:#131318;--fh-card-deep:#101014;--fh-input:#18181e;--fh-text:#f7f7fa;--fh-muted:#a4a4af;--fh-faint:#73737e;--fh-border:rgba(255,255,255,.085)}
    html,body,[data-testid="stAppViewContainer"],.stApp{background:var(--fh-bg)!important}
    [data-testid="stAppViewContainer"]{background:var(--fh-bg)!important}
    [data-testid="stAppViewContainer"]::before{display:none!important}
    [data-testid="stMainBlockContainer"]{max-width:1520px;padding:22px 26px 64px}
    [data-testid="stVerticalBlock"]{gap:.85rem}
    h1,h2,h3,[data-testid="stHeading"]{color:var(--fh-text);letter-spacing:-.035em}
    .app-header{display:flex;align-items:center;gap:14px;min-width:0;padding:4px 0 12px}
    .app-header__mark{width:42px;height:42px;flex:0 0 auto;display:grid;place-items:center;border:1px solid rgba(37,201,232,.25);border-radius:13px;background:#11171a;color:var(--fh-cyan);box-shadow:inset 0 1px 0 rgba(255,255,255,.055)}
    .app-header__mark svg{width:22px;height:22px}.app-header__copy{min-width:0;flex:1}.app-header__eyebrow{margin-bottom:3px;color:#8b8b96;font-size:9px;font-weight:800;letter-spacing:.15em;text-transform:uppercase}.app-header h1{margin:0;color:#fff;font-family:"Space Grotesk","Manrope",sans-serif;font-size:clamp(25px,2.5vw,32px);font-weight:700;line-height:1.05}.app-header p{margin:5px 0 0;color:#92929d;font-size:11.5px;line-height:1.45}
    .app-progress{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:1px 0 18px;padding:5px;border:1px solid rgba(255,255,255,.07);border-radius:15px;background:#0e0e12;box-shadow:inset 0 1px 0 rgba(255,255,255,.025)}
    .app-progress__item{position:relative;display:flex;align-items:center;gap:9px;min-width:0;padding:9px 11px;border-radius:11px;color:#858590}.app-progress__item:first-child{background:#17171d;color:#fff}.app-progress__number{width:23px;height:23px;flex:0 0 auto;display:grid;place-items:center;border:1px solid rgba(255,255,255,.11);border-radius:8px;background:#111116;color:#a9a9b4;font-size:9px;font-weight:800}.app-progress__item:first-child .app-progress__number{border-color:rgba(37,201,232,.30);background:rgba(37,201,232,.11);color:var(--fh-cyan)}.app-progress__copy strong{display:block;color:inherit;font-size:10.5px;font-weight:800}.app-progress__copy span{display:block;margin-top:1px;color:#696974;font-size:8px}
    [data-testid="stVerticalBlockBorderWrapper"]{border-color:rgba(255,255,255,.075)!important;border-radius:20px!important;background:#111115!important;box-shadow:0 1px 0 rgba(255,255,255,.025),0 18px 50px rgba(0,0,0,.18)!important}
    [data-testid="stVerticalBlockBorderWrapper"]>[data-testid="stVerticalBlock"]{padding:19px 20px!important}
    [data-testid="stVerticalBlockBorderWrapper"]:has(.app-header){overflow:visible;border:0!important;background:transparent!important;box-shadow:none!important}
    [data-testid="stVerticalBlockBorderWrapper"]:has(.app-header)>[data-testid="stVerticalBlock"]{padding:0!important}
    [data-testid="stVerticalBlockBorderWrapper"]:has(.app-header)::after{display:none!important}
    [data-testid="stVerticalBlockBorderWrapper"]:has(.preview-marker){top:18px;background:#0f0f13!important;box-shadow:0 20px 55px rgba(0,0,0,.28)!important}
    .st-key-pdf_card,.st-key-qr_card{min-height:236px}
    [data-testid="stVerticalBlockBorderWrapper"]:has(.card-accent)::before{top:22px;left:0;width:2px;height:42px;border-radius:0 3px 3px 0}
    .section-intro{margin:0 0 13px}.section-intro strong{font-size:15px;font-weight:700}.section-intro span{color:#898994;font-size:10px}.section-intro--accent{padding-left:0;margin-bottom:15px}.section-intro--accent::before{display:none}
    .section-intro--step{grid-template-columns:29px minmax(0,1fr);gap:10px}.section-intro__number{width:29px;height:29px;border-radius:9px!important;font-size:10px!important}
    [data-baseweb="input"]>div,[data-baseweb="select"]>div{min-height:44px;border:1px solid rgba(255,255,255,.075)!important;border-radius:12px!important;background:#18181e!important;box-shadow:inset 0 1px 0 rgba(255,255,255,.025)}
    [data-baseweb="input"]>div:hover,[data-baseweb="select"]>div:hover{border-color:rgba(255,255,255,.14)!important}
    [data-baseweb="input"]>div:focus-within,[data-baseweb="select"]>div:focus-within{border-color:rgba(37,201,232,.56)!important;box-shadow:0 0 0 3px rgba(37,201,232,.09)!important}
    [data-testid="stWidgetLabel"] p{color:#b8b8c2;font-size:10px;font-weight:650;letter-spacing:.01em}
    [data-testid="stFileUploaderDropzone"]{min-height:96px;border-color:rgba(37,201,232,.27)!important;border-radius:15px!important;background:#11181b!important;transform:none!important}
    [data-testid="stFileUploaderDropzone"]:hover{border-color:rgba(37,201,232,.54)!important;background:#131d20!important;transform:none!important}
    [data-testid="stFileUploaderDropzone"] button{border:1px solid rgba(37,201,232,.24)!important;border-radius:11px!important;background:rgba(37,201,232,.10)!important;box-shadow:none!important}
    .template-ready-zone{min-height:82px;padding:7px 2px}.template-ready-zone__icon{width:32px;height:32px;border-radius:10px}
    [data-testid="stRadio"],[data-testid="stSegmentedControl"]{color:#fff}
    [data-testid="stSegmentedControl"]>div{padding:3px;border:1px solid rgba(255,255,255,.07);border-radius:12px;background:#0d0d11}
    [data-testid="stSegmentedControl"] button{min-height:36px;border-radius:9px!important;font-size:11px;font-weight:700}
    [data-testid="stSegmentedControl"] button[aria-pressed="true"]{background:#24242b!important;color:#fff!important;box-shadow:0 1px 4px rgba(0,0,0,.28),inset 0 1px 0 rgba(255,255,255,.06)}
    .stButton>button,.stDownloadButton>button{min-height:42px;border-radius:12px!important;font-weight:750!important;transition:transform .15s ease,border-color .15s ease,background .15s ease,filter .15s ease}
    .stButton>button[kind="secondary"]{border:1px solid rgba(255,255,255,.09);background:#17171c;color:#e9e9ee;box-shadow:inset 0 1px 0 rgba(255,255,255,.035)}
    .stButton>button[kind="secondary"]:hover{border-color:rgba(255,255,255,.17);background:#1d1d23;color:#fff}
    .stButton>button[kind="primary"],.stDownloadButton>button[kind="primary"]{min-height:52px;background:var(--fh-pink)!important;box-shadow:0 10px 25px rgba(255,46,159,.20),inset 0 1px 0 rgba(255,255,255,.20)!important}
    .stButton>button[kind="primary"]:hover,.stDownloadButton>button[kind="primary"]:hover{filter:brightness(1.07);transform:translateY(-1px)}
    [data-testid="stAlert"]{border-color:rgba(255,255,255,.07)!important;border-radius:13px;background:#15151a!important}
    [data-testid="stImage"] img{border-color:rgba(255,255,255,.075);border-radius:12px}
    hr{display:none!important}
    .qr-process{border-radius:15px;background:#111814;box-shadow:none}.batch-summary__item,.completion-stat{background:#17171d}.seat-summary{background:#17171d}
    .st-key-preview_card [data-testid="stImage"]{padding:12px;border:1px solid rgba(255,255,255,.055);border-radius:15px;background:#08080a}.st-key-preview_card [data-testid="stImage"] img{max-height:690px;width:100%;object-fit:contain;border:0;border-radius:7px;box-shadow:0 15px 38px rgba(0,0,0,.36)}
    .st-key-preview_card [data-testid="stCaptionContainer"]{font-size:9.5px}.st-key-preview_card [data-testid="stWidgetLabel"] p{font-size:9px}
    @media(max-width:900px){[data-testid="stMainBlockContainer"]{padding:14px 12px 44px}.app-header{padding-top:1px}.app-header__mark{width:38px;height:38px;border-radius:12px}.app-header h1{font-size:25px}.app-header p{font-size:10.5px}.app-progress{grid-template-columns:repeat(4,1fr);gap:3px;margin-bottom:13px;padding:4px}.app-progress__item{justify-content:center;padding:8px 4px}.app-progress__copy span{display:none}.app-progress__copy strong{font-size:8.5px}.app-progress__number{width:21px;height:21px;border-radius:7px}[data-testid="stVerticalBlockBorderWrapper"]>[data-testid="stVerticalBlock"]{padding:16px!important}.st-key-pdf_card,.st-key-qr_card{min-height:0}}
    @media(max-width:560px){.app-progress__copy{display:none}.app-progress__item{padding:7px 3px}.app-header__eyebrow{font-size:8px}.app-header h1{font-size:23px}.app-header p{max-width:260px}.section-intro strong{font-size:14px}}

    /* Festholic Light — lenguaje visual claro inspirado en aplicaciones nativas */
    :root{--fh-bg:#f5f5f7;--fh-deep:#ffffff;--fh-panel:#ffffff;--fh-card:#ffffff;--fh-card-deep:#ffffff;--fh-input:#f5f5f7;--fh-text:#1d1d1f;--fh-muted:#6e6e73;--fh-faint:#86868b;--fh-border:rgba(0,0,0,.09);--fh-pink:#ff2e9f;--fh-orange:#ff7043;--fh-cyan:#00a9c4;--fh-green:#168a52}
    html,body,[data-testid="stAppViewContainer"],.stApp{background:#f5f5f7!important;color:#1d1d1f!important;font-family:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif!important}
    [data-testid="stAppViewContainer"]{background:#f5f5f7!important}
    h1,h2,h3,[data-testid="stHeading"],.app-header h1,.section-intro strong{color:#1d1d1f!important;font-family:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif!important;letter-spacing:-.035em}
    p,label,[data-testid="stCaptionContainer"]{color:#6e6e73}
    .app-header__mark{border-color:rgba(0,169,196,.22);background:#fff;color:#008da4;box-shadow:0 2px 10px rgba(0,0,0,.055),inset 0 1px 0 rgba(255,255,255,.7)}
    .app-header__eyebrow{color:#86868b}.app-header p{color:#6e6e73}
    .app-progress{border-color:rgba(0,0,0,.07);background:#fff;box-shadow:0 3px 16px rgba(0,0,0,.045)}
    .app-progress__item{color:#6e6e73}.app-progress__item:first-child{background:#1d1d1f;color:#fff}.app-progress__number{border-color:rgba(0,0,0,.08);background:#f0f0f2;color:#6e6e73}.app-progress__item:first-child .app-progress__number{border-color:rgba(255,255,255,.18);background:#00a9c4;color:#fff}.app-progress__copy span{color:#9a9aa0}.app-progress__item:first-child .app-progress__copy span{color:#c7c7cc}
    [data-testid="stVerticalBlockBorderWrapper"]{border-color:rgba(0,0,0,.075)!important;background:#fff!important;box-shadow:0 1px 2px rgba(0,0,0,.025),0 12px 36px rgba(0,0,0,.055)!important}
    [data-testid="stVerticalBlockBorderWrapper"]:has(.app-header){background:transparent!important;box-shadow:none!important}
    [data-testid="stVerticalBlockBorderWrapper"]:has(.preview-marker){background:#fff!important;box-shadow:0 14px 42px rgba(0,0,0,.075)!important}
    .section-intro strong{color:#1d1d1f!important}.section-intro span{color:#77777d}
    .section-intro__number{box-shadow:none!important}.section-intro--pink .section-intro__number{border-color:rgba(255,46,159,.22);color:#d51278!important;background:#fff0f8}.section-intro--cyan .section-intro__number{border-color:rgba(0,169,196,.24);color:#007e92!important;background:#ebfafc}.section-intro--orange .section-intro__number{border-color:rgba(255,112,67,.25);color:#d94b1d!important;background:#fff3ef}
    [data-baseweb="input"]>div,[data-baseweb="select"]>div{border-color:rgba(0,0,0,.085)!important;background:#f5f5f7!important;box-shadow:inset 0 1px 1px rgba(0,0,0,.018)}
    [data-baseweb="input"]>div:hover,[data-baseweb="select"]>div:hover{border-color:rgba(0,0,0,.16)!important}
    [data-baseweb="input"]>div:focus-within,[data-baseweb="select"]>div:focus-within{border-color:rgba(0,169,196,.55)!important;box-shadow:0 0 0 3px rgba(0,169,196,.10)!important}
    [data-baseweb="input"] input,[data-baseweb="select"] *{color:#1d1d1f!important}
    [data-testid="stWidgetLabel"] p{color:#515157!important}
    [data-testid="stFileUploaderDropzone"]{border-color:rgba(0,169,196,.34)!important;background:#f0fbfd!important}
    [data-testid="stFileUploaderDropzone"]::before,[data-testid="stFileUploaderDropzoneInstructions"] span{color:#1d1d1f!important}
    [data-testid="stFileUploaderDropzoneInstructions"] small{color:#74747b!important}
    [data-testid="stFileUploaderDropzone"]:hover{border-color:#00a9c4!important;background:#e8f8fb!important}
    [data-testid="stFileUploaderDropzone"] svg{color:#008da4!important;fill:#008da4!important}
    [data-testid="stFileUploaderDropzone"] button{border-color:#00a9c4!important;background:#00a9c4!important;color:#fff!important;box-shadow:0 5px 14px rgba(0,169,196,.20)!important}
    [data-testid="stFileUploaderDropzone"] button::after{color:#fff!important}
    .st-key-event_image_upload [data-testid="stFileUploaderDropzone"]{border-color:rgba(255,112,67,.34)!important;background:#fff6f2!important}.st-key-event_image_upload [data-testid="stFileUploaderDropzone"]:hover{border-color:#ff7043!important;background:#fff0e9!important}.st-key-event_image_upload [data-testid="stFileUploaderDropzone"] svg{color:#e95728!important;fill:#e95728!important}.st-key-event_image_upload [data-testid="stFileUploaderDropzone"] button{border-color:#ff7043!important;background:#ff7043!important;color:#fff!important;box-shadow:0 5px 14px rgba(255,112,67,.20)!important}
    [data-testid="stFileUploaderFile"],[data-testid="stFileChip"]{border-color:rgba(0,0,0,.08)!important;background:#fff!important;color:#1d1d1f!important}
    .template-ready-zone{color:#174d32}.template-ready-zone__icon{background:#e4f7ec;color:#168a52}.template-ready-zone small{color:#698072}
    [data-testid="stSegmentedControl"]>div{border-color:rgba(0,0,0,.07);background:#ececf0}
    [data-testid="stSegmentedControl"] button{color:#5c5c62!important}
    [data-testid="stSegmentedControl"] button[aria-pressed="true"]{background:#fff!important;color:#1d1d1f!important;box-shadow:0 1px 5px rgba(0,0,0,.12),inset 0 1px 0 rgba(255,255,255,.8)}
    [role="radiogroup"] label{color:#515157!important}[role="radiogroup"] label:has(input:checked){color:#007e92!important}
    .stButton>button[kind="secondary"]{border-color:#1d1d1f!important;background:#1d1d1f!important;color:#fff!important;box-shadow:0 5px 14px rgba(0,0,0,.13)!important}.stButton>button[kind="secondary"] *,.stButton>button[kind="secondary"] p{color:#fff!important}.stButton>button[kind="secondary"]:hover{border-color:#333336!important;background:#333336!important;color:#fff!important}
    .stButton>button[kind="primary"],.stDownloadButton>button[kind="primary"]{border-color:#ff2e9f!important;background:#ff2e9f!important;color:#fff!important;box-shadow:0 8px 20px rgba(255,46,159,.20)!important}
    .stButton>button:disabled{border-color:#d8d8dc!important;background:#e5e5e9!important;color:#98989e!important;box-shadow:none!important}.stButton>button:disabled *{color:#98989e!important}
    [data-testid="stAlert"]{border-color:rgba(0,0,0,.07)!important;background:#f7f7f9!important;color:#1d1d1f!important}
    [data-testid="stAlert"] p{color:#4f4f55!important}
    [data-testid="stImage"] img{border-color:rgba(0,0,0,.08)}
    .qr-process{border-color:#bce7cf;background:#f0faf4;box-shadow:none}.qr-process__icon{background:#daf2e4;color:#168a52}.qr-process__head strong,.qr-process__step b{color:#173d29}.qr-process__head small,.qr-process__step small,.qr-process__more summary{color:#66786d}.qr-process__step>span{border-color:#a9ddc0;background:#e8f7ee;color:#168a52}.qr-process__approved{border-color:rgba(0,0,0,.07);color:#168a52}
    .batch-summary__item,.completion-stat,.seat-summary{border-color:rgba(0,0,0,.07);background:#f5f5f7}.batch-summary__item strong,.completion-stat strong,.seat-summary__top b{color:#1d1d1f}
    .st-key-seat_slots [class*="st-key-seat_slot_"]{border-color:rgba(0,0,0,.07);background:#f7f7f9}.seat-badge{background:#e7f8fb;color:#007e92}.seat-badge--ok{background:#e4f7ec;color:#168a52}.seat-badge--bad{background:#fff0ea;color:#d94b1d}
    .st-key-preview_card [data-testid="stImage"]{border-color:rgba(0,0,0,.065);background:#ececf0}.st-key-preview_card [data-testid="stImage"] img{box-shadow:0 15px 38px rgba(0,0,0,.16)}
    [data-testid="stDialog"]:has(.completion-modal) [role="dialog"]{border-color:rgba(0,0,0,.10);background:#fff;box-shadow:0 30px 80px rgba(0,0,0,.20)}.completion-modal__title{color:#1d1d1f}.completion-modal__copy{color:#6e6e73}
    .support-card{border-color:rgba(255,112,67,.22);background:#fff7f3}.support-card strong{color:#1d1d1f}.support-card p{color:#6e6e73}.support-card__account{color:#1d1d1f}

    /* Tema final oscuro: elimina las superficies blancas y conserva la estructura tipo app */
    :root{--fh-bg:#09090b;--fh-deep:#09090b;--fh-panel:#101014;--fh-card:#131318;--fh-card-deep:#101014;--fh-input:#18181e;--fh-text:#f7f7fa;--fh-muted:#a4a4af;--fh-faint:#73737e;--fh-border:rgba(255,255,255,.085);--fh-pink:#ff2e9f;--fh-orange:#ff7043;--fh-cyan:#25c9e8;--fh-green:#51d98a}
    html,body,[data-testid="stAppViewContainer"],.stApp{background:#09090b!important;color:#f7f7fa!important;font-family:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif!important}
    [data-testid="stAppViewContainer"]{background:#09090b!important}
    h1,h2,h3,[data-testid="stHeading"],.app-header h1,.section-intro strong{color:#f7f7fa!important}
    p,label,[data-testid="stCaptionContainer"]{color:#a4a4af}
    .app-header__mark{border-color:rgba(37,201,232,.25);background:#11171a;color:#25c9e8;box-shadow:inset 0 1px 0 rgba(255,255,255,.055)}
    .app-header__eyebrow{color:#8b8b96}.app-header p{color:#92929d}
    .app-progress{border-color:rgba(255,255,255,.07);background:#0e0e12;box-shadow:inset 0 1px 0 rgba(255,255,255,.025)}
    .app-progress__item{color:#858590}.app-progress__item:first-child{background:#17171d;color:#fff}.app-progress__number{border-color:rgba(255,255,255,.11);background:#111116;color:#a9a9b4}.app-progress__item:first-child .app-progress__number{border-color:rgba(37,201,232,.30);background:#25c9e8;color:#071519}.app-progress__copy span{color:#696974}.app-progress__item:first-child .app-progress__copy span{color:#9a9aa5}
    [data-testid="stVerticalBlockBorderWrapper"]{border-color:rgba(255,255,255,.075)!important;background:#111115!important;box-shadow:0 1px 0 rgba(255,255,255,.025),0 18px 50px rgba(0,0,0,.18)!important}
    [data-testid="stVerticalBlockBorderWrapper"]:has(.app-header){background:transparent!important;box-shadow:none!important}
    [data-testid="stVerticalBlockBorderWrapper"]:has(.preview-marker){background:#0f0f13!important;box-shadow:0 20px 55px rgba(0,0,0,.28)!important}
    .section-intro strong{color:#f7f7fa!important}.section-intro span{color:#898994}.section-intro__number{box-shadow:none!important}.section-intro--pink .section-intro__number{border-color:rgba(255,46,159,.36);color:#ff70b9!important;background:rgba(255,46,159,.12)}.section-intro--cyan .section-intro__number{border-color:rgba(37,201,232,.34);color:#25c9e8!important;background:rgba(37,201,232,.11)}.section-intro--orange .section-intro__number{border-color:rgba(255,112,67,.38);color:#ff9a78!important;background:rgba(255,112,67,.12)}
    [data-baseweb="input"]>div,[data-baseweb="select"]>div{border-color:rgba(255,255,255,.075)!important;background:#18181e!important;box-shadow:inset 0 1px 0 rgba(255,255,255,.025)}
    [data-baseweb="input"]>div:hover,[data-baseweb="select"]>div:hover{border-color:rgba(255,255,255,.14)!important}[data-baseweb="input"]>div:focus-within,[data-baseweb="select"]>div:focus-within{border-color:rgba(37,201,232,.56)!important;box-shadow:0 0 0 3px rgba(37,201,232,.09)!important}
    [data-baseweb="input"] input,[data-baseweb="select"] *{color:#f7f7fa!important}[data-testid="stWidgetLabel"] p{color:#b8b8c2!important}
    [data-testid="stFileUploaderDropzone"]{border-color:rgba(37,201,232,.32)!important;background:#11181b!important}[data-testid="stFileUploaderDropzone"]::before,[data-testid="stFileUploaderDropzoneInstructions"] span{color:#f7f7fa!important}[data-testid="stFileUploaderDropzoneInstructions"] small{color:#92929d!important}[data-testid="stFileUploaderDropzone"]:hover{border-color:#25c9e8!important;background:#131d20!important}[data-testid="stFileUploaderDropzone"] svg{color:#25c9e8!important;fill:#25c9e8!important}
    [data-testid="stFileUploaderDropzone"] button{border-color:#25c9e8!important;background:#25c9e8!important;color:#071519!important;box-shadow:0 6px 16px rgba(37,201,232,.20)!important}[data-testid="stFileUploaderDropzone"] button::after{color:#071519!important}
    .st-key-event_image_upload [data-testid="stFileUploaderDropzone"]{border-color:rgba(255,112,67,.34)!important;background:#1b1513!important}.st-key-event_image_upload [data-testid="stFileUploaderDropzone"]:hover{border-color:#ff7043!important;background:#211713!important}.st-key-event_image_upload [data-testid="stFileUploaderDropzone"] svg{color:#ff7043!important;fill:#ff7043!important}.st-key-event_image_upload [data-testid="stFileUploaderDropzone"] button{border-color:#ff7043!important;background:#ff7043!important;color:#fff!important;box-shadow:0 6px 16px rgba(255,112,67,.20)!important}.st-key-event_image_upload [data-testid="stFileUploaderDropzone"] button::after{color:#fff!important}
    [data-testid="stFileUploaderFile"],[data-testid="stFileChip"]{border-color:rgba(255,255,255,.08)!important;background:#17171c!important;color:#f7f7fa!important}.template-ready-zone{color:#dffbec}.template-ready-zone__icon{background:rgba(81,217,138,.16);color:#51d98a}.template-ready-zone small{color:rgba(223,251,236,.64)}
    [data-testid="stSegmentedControl"]>div{border-color:rgba(255,255,255,.07);background:#0d0d11}[data-testid="stSegmentedControl"] button{color:#aaaab4!important}[data-testid="stSegmentedControl"] button[aria-pressed="true"]{background:#292930!important;color:#fff!important;box-shadow:0 1px 5px rgba(0,0,0,.30),inset 0 1px 0 rgba(255,255,255,.07)}[role="radiogroup"] label{color:#b8b8c2!important}[role="radiogroup"] label:has(input:checked){color:#25c9e8!important}
    .stButton>button[kind="secondary"]{border-color:#2b2b32!important;background:#24242a!important;color:#fff!important;box-shadow:inset 0 1px 0 rgba(255,255,255,.05)!important}.stButton>button[kind="secondary"] *,.stButton>button[kind="secondary"] p{color:#fff!important}.stButton>button[kind="secondary"]:hover{border-color:#3a3a43!important;background:#303037!important;color:#fff!important}
    .stButton>button[kind="primary"],.stDownloadButton>button[kind="primary"]{border-color:#ff2e9f!important;background:#ff2e9f!important;color:#fff!important;box-shadow:0 9px 22px rgba(255,46,159,.22)!important}.stButton>button:disabled{border-color:#2d2d33!important;background:#25252b!important;color:#777b84!important;box-shadow:none!important}.stButton>button:disabled *{color:#777b84!important}
    [data-testid="stAlert"]{border-color:rgba(255,255,255,.07)!important;background:#15151a!important;color:#f7f7fa!important}[data-testid="stAlert"] p{color:#c4c4cc!important}[data-testid="stImage"] img{border-color:rgba(255,255,255,.075)}
    .qr-process{border-color:rgba(81,217,138,.25);background:#111814;box-shadow:none}.qr-process__icon{background:rgba(81,217,138,.14);color:#51d98a}.qr-process__head strong,.qr-process__step b{color:#edf7f1}.qr-process__head small,.qr-process__step small,.qr-process__more summary{color:#8fa097}.qr-process__step>span{border-color:rgba(81,217,138,.35);background:#17241d;color:#51d98a}.qr-process__approved{border-color:rgba(255,255,255,.07);color:#51d98a}
    .batch-summary__item,.completion-stat,.seat-summary{border-color:rgba(255,255,255,.08);background:#17171d}.batch-summary__item strong,.completion-stat strong,.seat-summary__top b{color:#fff}.st-key-seat_slots [class*="st-key-seat_slot_"]{border-color:rgba(255,255,255,.08);background:#15161c}.seat-badge{background:rgba(37,201,232,.12);color:#25c9e8}.seat-badge--ok{background:rgba(81,217,138,.18);color:#51d98a}.seat-badge--bad{background:rgba(255,112,67,.18);color:#ff7043}
    .st-key-preview_card [data-testid="stImage"]{border-color:rgba(255,255,255,.055);background:#08080a}.st-key-preview_card [data-testid="stImage"] img{box-shadow:0 15px 38px rgba(0,0,0,.36)}
    [data-testid="stDialog"]:has(.completion-modal) [role="dialog"]{border-color:rgba(255,255,255,.11);background:#131318;box-shadow:0 30px 80px rgba(0,0,0,.48)}.completion-modal__title{color:#fff}.completion-modal__copy{color:#a4a4af}.support-card{border-color:rgba(255,112,67,.20);background:#171719}.support-card strong{color:#fff}.support-card p{color:#a4a4af}.support-card__account{color:#fff}
    .app-visual{position:relative;min-height:142px;overflow:hidden;display:grid;grid-template-columns:minmax(0,1fr) minmax(260px,42%);align-items:center;gap:20px;margin:-3px 0 18px;padding:20px 22px;border:1px solid rgba(255,255,255,.08);border-radius:18px;background:radial-gradient(circle at 85% 20%,rgba(37,201,232,.14),transparent 12rem),radial-gradient(circle at 60% 110%,rgba(255,46,159,.12),transparent 13rem),#101014;box-shadow:0 18px 42px rgba(0,0,0,.22)}.app-visual::after{content:"";position:absolute;left:22px;top:0;width:150px;height:3px;background:linear-gradient(90deg,#ff2e9f 0 38%,#ff7043 38% 68%,#25c9e8 68% 100%)}.app-visual__copy{position:relative;z-index:1;max-width:430px}.app-visual__copy strong{display:block;color:#fff;font-family:"Space Grotesk","Manrope",sans-serif;font-size:19px;letter-spacing:-.025em}.app-visual__copy span{display:block;margin-top:5px;color:#a9a9b4;font-size:10.5px;line-height:1.5}.app-visual__art{position:relative;min-height:100px}.visual-ticket{position:absolute;display:grid;grid-template-columns:1fr 50px;align-items:center;width:176px;height:84px;padding:12px;border:1px solid rgba(255,255,255,.16);border-radius:13px;background:linear-gradient(145deg,#23232b,#15151a);box-shadow:0 13px 28px rgba(0,0,0,.32)}.visual-ticket::before,.visual-ticket::after{content:"";position:absolute;right:48px;width:13px;height:13px;border-radius:50%;background:#101014}.visual-ticket::before{top:-7px}.visual-ticket::after{bottom:-7px}.visual-ticket--back{right:80px;top:8px;transform:rotate(-9deg);opacity:.58}.visual-ticket--front{right:16px;top:13px;transform:rotate(5deg)}.visual-ticket__lines{display:grid;gap:7px}.visual-ticket__lines i{display:block;height:5px;border-radius:4px;background:rgba(255,255,255,.13)}.visual-ticket__lines i:first-child{width:76%;background:#ff2e9f}.visual-ticket__lines i:nth-child(2){width:92%}.visual-ticket__lines i:nth-child(3){width:55%;background:rgba(37,201,232,.65)}.visual-ticket__qr{width:40px;height:40px;color:#fff}.visual-scan{position:absolute;right:0;bottom:0;width:32px;height:32px;color:#25c9e8}.visual-download{position:absolute;right:220px;bottom:2px;width:28px;height:28px;color:#ff7043}
    .completion-modal{min-height:116px;overflow:hidden;padding:18px 42% 18px 18px!important;border-radius:15px;background:radial-gradient(circle at 90% 25%,rgba(37,201,232,.16),transparent 9rem),#101014}.completion-modal__copy{color:#b8b8c2!important}.completion-modal__art{position:absolute;right:24px;top:18px;width:128px;height:80px;color:#25c9e8}.completion-modal__art .ticket-body{fill:#1d1d24;stroke:#ff2e9f;stroke-width:1.4}.completion-modal__art .ticket-line{stroke:#6f707b;stroke-width:1.2}.completion-modal__art .ticket-qr{fill:#fff}.completion-modal__art .ticket-check{fill:#51d98a}
    @media(max-width:700px){.app-visual{grid-template-columns:1fr;min-height:220px}.app-visual__art{min-height:105px}.visual-ticket--back{right:92px}.visual-ticket--front{right:28px}.visual-download{right:230px}.completion-modal{padding-right:34%!important}.completion-modal__art{right:12px;width:104px}}@media(max-width:420px){.app-visual{min-height:210px;padding:17px}.app-visual__copy strong{font-size:17px}.visual-ticket{width:154px;height:76px}.visual-ticket--back{right:65px}.visual-ticket--front{right:8px}.visual-download{display:none}.completion-modal{padding:16px!important}.completion-modal__art{display:none}}
    </style>
    """,
    unsafe_allow_html=True,
)

def current_festholic_token() -> str:
    value = st.query_params.get("festholic_token", "")
    return str(value[0] if isinstance(value, list) and value else value or "")


@st.cache_data(show_spinner=False)
def digitalize_qr(data: bytes):
    raw = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("El archivo no pudo interpretarse como una imagen válida.")
    return image, process_image(image)


@st.cache_data(show_spinner=False, max_entries=300)
def build_ticket_pdf(pdf_data: bytes, fields: dict, event_image: bytes | None, image_mode: str, qr_png: bytes) -> bytes:
    """Genera un PDF y lo guarda en caché: solo se rehacen las entradas que cambian."""
    return edit_ticket_fields(
        pdf_data, fields, event_image=event_image, image_mode=image_mode, reconstructed_qr=qr_png
    )


def section_intro(title: str, description: str, accent: str | None = None, step: int | None = None) -> None:
    accent_class = f" section-intro--accent section-intro--{accent}" if accent else ""
    step_class = " section-intro--step" if step is not None else ""
    content = f'<strong>{title}</strong><span>{description}</span>'
    if step is not None:
        content = f'<span class="section-intro__number">{step}</span><div class="section-intro__copy">{content}</div>'
    st.markdown(
        f'<div class="section-intro{accent_class}{step_class}">{content}</div>',
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def pdf_page_count(data: bytes) -> int:
    return count_pdf_pages(data)


@st.cache_data(show_spinner=False)
def render_pdf_page(data: bytes, page_index: int, zoom: float) -> bytes:
    return render_page_png(data, page_index, zoom)


def new_ticket_identity() -> dict[str, str]:
    return {
        "number": str(10_000 + secrets.randbelow(90_000)),
        "code": "".join(str(secrets.randbelow(10)) for _ in range(16)),
        "purchase": str(10_000_000 + secrets.randbelow(90_000_000)),
        "ticket": str(10_000_000 + secrets.randbelow(90_000_000)),
        "transaction": secrets.token_hex(10).upper(),
        "purchase_date": current_purchase_timestamp(),
    }


def current_purchase_timestamp() -> str:
    """Fecha de emisión en la zona horaria de Festholic (Lima)."""
    return datetime.now(ZoneInfo("America/Lima")).strftime("%d/%m/%Y - %I:%M:%S %p")


def rotate_ticket_identity() -> None:
    """Prepara identificadores nuevos después de entregar cada descarga."""
    st.session_state.ticket_identity = new_ticket_identity()


def qr_file_key(name: str, data: bytes) -> str:
    """Identificador estable para conservar los números durante cada edición."""
    digest = hashlib.sha256(data).hexdigest()[:20]
    return f"{name}:{digest}"


def batch_ticket_identity(key: str) -> dict[str, str]:
    identities = st.session_state.setdefault("batch_ticket_identities", {})
    if key not in identities:
        identities[key] = new_ticket_identity()
    return identities[key]


def rotate_batch_identities() -> None:
    """Hace que el siguiente ZIP utilice identificadores visibles nuevos."""
    st.session_state.batch_ticket_identities = {}


def festholic_tracking_token() -> str:
    return current_festholic_token()


def register_generation(entry_count: int, mode: str, event_id: str) -> bool:
    """Registra la descarga únicamente cuando existe una sesión firmada por Festholic."""
    token = festholic_tracking_token()
    if not token:
        return False
    payload = json.dumps({
        "token": token,
        "eventId": event_id,
        "entryCount": entry_count,
        "mode": mode,
    }).encode("utf-8")
    request = Request(
        FESTHOLIC_GENERATION_ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "Festholic-Digitalizer/1.0"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            return 200 <= response.status < 300
    except (HTTPError, URLError, TimeoutError, ValueError):
        return False


def complete_download(entry_count: int, mode: str) -> None:
    event_id = st.session_state.setdefault("download_event_id", str(uuid.uuid4()))
    st.session_state.last_generation_tracked = register_generation(entry_count, mode, event_id)
    st.session_state.download_event_id = str(uuid.uuid4())
    if mode == "batch":
        rotate_batch_identities()
    else:
        rotate_ticket_identity()


def safe_pdf_filename(value: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", value).strip().rstrip(".")
    if name.lower().endswith(".pdf"):
        name = name[:-4].strip().rstrip(".")
    return f"{name or 'E-ticket'}.pdf"


def safe_filename_stem(value: str, fallback: str = "E-ticket") -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", value).strip().rstrip(".")
    if name.lower().endswith(".zip"):
        name = name[:-4].strip().rstrip(".")
    return name or fallback


def default_ticket_name(row: str = "", seat: str = "") -> str:
    """Construye el nombre automático con la ubicación cuando corresponde."""
    parts = ["E-ticket"]
    if seat.strip():
        parts.extend(["Asiento", safe_filename_stem(seat.strip(), "x")])
    if row.strip():
        parts.extend(["Fila", safe_filename_stem(row.strip(), "x")])
    return "-".join(parts)


def build_ticket_zip(entries: list[tuple[str, bytes]]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, pdf_bytes in entries:
            archive.writestr(filename, pdf_bytes)
    return output.getvalue()


def render_pdf_preview(data: bytes | None) -> None:
    if not data:
        st.info("Selecciona un PDF para mostrar la vista previa.")
        return
    try:
        total_pages = pdf_page_count(data)
        document_key = hashlib.sha256(data).hexdigest()[:12]
        page_column, zoom_column = st.columns([1, 1.25])
        with page_column:
            page_number = st.selectbox(
                "Página",
                options=list(range(1, total_pages + 1)),
                key=f"preview_page_{document_key}",
            )
        with zoom_column:
            zoom = st.select_slider(
                "Zoom",
                options=[1.0, 1.25, 1.5, 1.75, 2.0],
                value=1.25,
                format_func=lambda value: f"{round(value * 100)}%",
                key="preview_zoom",
            )
        image = render_pdf_page(data, page_number - 1, zoom)
        st.image(image, caption=f"Página {page_number} de {total_pages}", width="stretch")
        st.caption("La vista se actualiza automáticamente. Usa el icono de ampliar de la imagen para verla en pantalla completa.")
    except (ValueError, RuntimeError) as error:
        st.error(f"No se pudo renderizar la vista previa: {error}", icon="🚨")


@st.dialog("Cómo usar el digitalizador")
def show_tutorial() -> None:
    st.markdown("""
    1. Selecciona una plantilla Teleticket, Ticketmaster o Joinnus, o carga un PDF compatible.
    2. Elige si generarás una entrada o varias entradas en un lote.
    3. Sube una o varias fotografías claras de los QR físicos, con los cuatro bordes visibles.
    4. Espera la validación y revisa los resultados.
    5. Actualiza los datos y la imagen del evento.
    6. Pulsa **Digitalizar entrada** para revisar el resumen y descargar el PDF o el ZIP del lote.

    Si son entradas con asiento, elige "Varias entradas", marca "Son entradas con asiento" e indica la fila y el asiento de cada QR.

    El archivo original no se modifica.
    """)


@st.dialog(
    "Digitalización completada",
    width="large",
    icon=":material/task_alt:",
)
def show_generation_dialog(
    *,
    entry_names: list[str],
    download_data: bytes,
    download_filename: str,
    download_mime: str,
    mode: str,
    event_name: str,
    source_name: str,
    errors: list[str] | None = None,
) -> None:
    """Muestra el cierre del proceso y concentra la descarga en un solo lugar."""
    errors = errors or []
    entry_count = len(entry_names)
    plural = entry_count != 1
    noun = "entradas" if plural else "entrada"
    download_label = "Descargar entradas" if plural else "Descargar entrada"

    st.markdown(
        f"""
        <div class="completion-modal">
          <div class="completion-modal__eyebrow">Proceso finalizado</div>
          <div class="completion-modal__title">{entry_count} {noun} {"listas" if plural else "lista"}</div>
          <p class="completion-modal__copy">Los códigos QR fueron validados y los documentos ya están preparados para descargar.</p>
          <svg class="completion-modal__art" viewBox="0 0 140 90" aria-hidden="true">
            <path class="ticket-body" d="M12 16h116v17a9 9 0 0 0 0 18v23H12V51a9 9 0 0 0 0-18V16Z"/>
            <path class="ticket-line" d="M73 20v50M23 29h35M23 39h26M23 49h31"/>
            <path class="ticket-qr" d="M86 27h14v14H86zm4 4v6h6v-6zm15-4h14v14h-14zm4 4v6h6v-6zM86 46h14v14H86zm4 4v6h6v-6zm16-3h5v5h-5zm7 7h6v6h-6zm-8 4h5v5h-5z"/>
            <circle class="ticket-check" cx="119" cy="18" r="10"/><path d="m114 18 3 3 6-7" fill="none" stroke="#07140d" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.status("Proceso completado", state="complete", expanded=True):
        st.write(":material/check_circle: Códigos QR detectados y validados")
        st.write(":material/check_circle: Información aplicada a la plantilla")
        st.write(f":material/check_circle: {entry_count} PDF {'generados' if plural else 'generado'} correctamente")
        if mode == "batch":
            st.write(":material/check_circle: Archivos organizados en un ZIP")

    st.markdown(
        f"""
        <div class="completion-stats">
          <div class="completion-stat"><strong>{entry_count + len(errors)}</strong><span>Procesadas</span></div>
          <div class="completion-stat completion-stat--ok"><strong>{entry_count}</strong><span>Listas para descargar</span></div>
          <div class="completion-stat completion-stat--warn"><strong>{len(errors)}</strong><span>Requieren revisión</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.subheader("Resumen de la digitalización", icon=":material/receipt_long:")
        st.caption(f"{event_name or 'Evento'} · {source_name}")
        for index, filename in enumerate(entry_names, start=1):
            name_column, status_column = st.columns([5, 1], vertical_alignment="center")
            name_column.text(f"{index:02d}. {filename}")
            status_column.badge("Lista", icon=":material/check:", color="green")
        if errors:
            with st.expander(
                f"{len(errors)} entrada(s) requieren revisión",
                icon=":material/warning:",
            ):
                for message in errors:
                    st.write(f"- {message}")

    st.download_button(
        download_label,
        data=download_data,
        file_name=download_filename,
        mime=download_mime,
        type="primary",
        icon=":material/download:",
        width="stretch",
        on_click="ignore",
        key=f"modal_download_{mode}_{download_filename}",
    )
    st.caption("Guarda tus entradas en un lugar seguro y no compartas sus códigos QR.")

    st.markdown(
        """
        <div class="support-card">
          <div class="support-card__label">Apoya esta herramienta</div>
          <strong>¿Te fue útil? Puedes dejarnos una propina</strong>
          <p>Tu apoyo es opcional y nos ayuda mucho a seguir manteniendo y mejorando el digitalizador.</p>
          <div class="support-card__account">
            <span>Yape o Plin</span><span>968 424 445</span><span>Keenscy Sanchez</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


with st.container(border=False):
    title_column, help_column = st.columns([8, 2], vertical_alignment="center")
    with title_column:
        st.markdown("""
        <div class="app-header">
          <span class="app-header__mark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3h-3zM18 18h3v3h-3zM18 14h3M14 20h2"/></svg></span>
          <span class="app-header__copy"><span class="app-header__eyebrow">Festholic tools</span><h1>Digitalizador de entradas</h1><p>Reconstruye el QR, personaliza la entrada y descarga el resultado.</p></span>
        </div>
        """, unsafe_allow_html=True)
    with help_column:
        if st.button("Guía", icon=":material/help_outline:", width="stretch"):
            show_tutorial()

st.markdown(
    """
    <div class="app-progress" aria-label="Flujo de digitalización">
      <div class="app-progress__item"><span class="app-progress__number">01</span><span class="app-progress__copy"><strong>Plantilla</strong><span>Elige el formato</span></span></div>
      <div class="app-progress__item"><span class="app-progress__number">02</span><span class="app-progress__copy"><strong>Código QR</strong><span>Sube y valida</span></span></div>
      <div class="app-progress__item"><span class="app-progress__number">03</span><span class="app-progress__copy"><strong>Personaliza</strong><span>Edita los datos</span></span></div>
      <div class="app-progress__item"><span class="app-progress__number">04</span><span class="app-progress__copy"><strong>Exporta</strong><span>Revisa y descarga</span></span></div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="app-visual" role="img" aria-label="Ilustración de entradas digitales y código QR">
      <div class="app-visual__copy">
        <strong>Entradas listas para volver al evento</strong>
        <span>Del QR físico a un E-ticket claro, personalizado y preparado para descargar.</span>
      </div>
      <div class="app-visual__art" aria-hidden="true">
        <div class="visual-ticket visual-ticket--back"><span class="visual-ticket__lines"><i></i><i></i><i></i></span><svg class="visual-ticket__qr" viewBox="0 0 24 24"><path fill="currentColor" d="M3 3h8v8H3V3Zm2 2v4h4V5H5Zm8-2h8v8h-8V3Zm2 2v4h4V5h-4ZM3 13h8v8H3v-8Zm2 2v4h4v-4H5Zm9-2h3v3h-3v-3Zm4 0h3v3h-3v-3Zm-5 5h3v3h-3v-3Zm5 0h3v3h-3v-3Z"/></svg></div>
        <div class="visual-ticket visual-ticket--front"><span class="visual-ticket__lines"><i></i><i></i><i></i></span><svg class="visual-ticket__qr" viewBox="0 0 24 24"><path fill="currentColor" d="M3 3h8v8H3V3Zm2 2v4h4V5H5Zm8-2h8v8h-8V3Zm2 2v4h4V5h-4ZM3 13h8v8H3v-8Zm2 2v4h4v-4H5Zm9-2h3v3h-3v-3Zm4 0h3v3h-3v-3Zm-5 5h3v3h-3v-3Zm5 0h3v3h-3v-3Z"/></svg></div>
        <svg class="visual-scan" viewBox="0 0 24 24"><path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
        <svg class="visual-download" viewBox="0 0 24 24"><path d="M12 3v12m0 0 4-4m-4 4-4-4M5 20h14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


pdf_data: bytes | None = None
pdf_name = "plantilla-teleticket.pdf"
pdf_source = "Plantilla Teleticket"
qr_file = None
qr_files = []
qr_png = None
qr_ready = False
qr_original = None
qr_result = None
qr_error = None
qr_items = []
edited_pdf: bytes | None = None
batch_entries: list[tuple[str, bytes]] = []
batch_generation_errors: list[str] = []
generation_error = None
seat_mode = False
seat_count = 0
batch_seat_labels: dict[str, str] = {}

if "ticket_identity" not in st.session_state:
    st.session_state.ticket_identity = new_ticket_identity()
ticket_identity = st.session_state.ticket_identity
if any(name not in ticket_identity for name in ("purchase", "ticket", "transaction", "purchase_date")):
    ticket_identity.update(new_ticket_identity())

editor_column, preview_column = st.columns([64, 36], gap="medium")

with editor_column:
    source_left, source_right = st.columns(2, gap="small")
    with source_left:
        with st.container(border=True, key="pdf_card"):
            st.markdown('<div class="card-accent card-accent--pdf"></div>', unsafe_allow_html=True)
            section_intro("PDF de la entrada", "Usa una plantilla incluida o sube un PDF compatible.", "pink", 1)
            pdf_source = st.selectbox(
                "Plantilla base",
                ["Plantilla Teleticket", "Plantilla Ticketmaster", "Plantilla Joinnus", "Subir otro PDF"],
                key="pdf_source",
            )
            if pdf_source in DEFAULT_TEMPLATE_PATHS:
                template_path = DEFAULT_TEMPLATE_PATHS[pdf_source]
                if template_path.exists():
                    pdf_data = template_path.read_bytes()
                    pdf_name = template_path.name
                    with st.container(key="pdf_ready"):
                        st.markdown(
                            f'<div class="template-ready-zone"><span class="template-ready-zone__icon">✓</span><span>{template_path.name}<small>Plantilla cargada y lista para editar</small></span></div>',
                            unsafe_allow_html=True,
                        )
                else:
                    st.error("No se encontró la plantilla incluida.")
            else:
                with st.container(key="pdf_upload"):
                    pdf_file = st.file_uploader("Arrastra tu PDF aquí o selecciónalo", type=["pdf"], key="pdf_file", help="Se conservarán el diseño y los códigos de control.", label_visibility="collapsed")
                if pdf_file is not None:
                    pdf_data = pdf_file.getvalue()
                    pdf_name = pdf_file.name
                    st.caption(f"{pdf_file.name} · {len(pdf_data)/(1024*1024):.2f} MB")

    with source_right:
        with st.container(border=True, key="qr_card"):
            st.markdown('<div class="card-accent card-accent--qr"></div>', unsafe_allow_html=True)
            section_intro("Fotografía del código QR", "Sube un QR o genera varias entradas en un solo lote.", "cyan", 2)
            generation_mode = st.segmented_control(
                "Tipo de generación",
                ["Una entrada", "Varias entradas"],
                default="Una entrada",
                key="generation_mode",
                width="stretch",
            )
            if generation_mode == "Varias entradas":
                seat_mode = st.toggle(
                    "Son entradas con asiento (fila y asiento distintos)",
                    key="batch_seat_mode",
                    help="Podrás indicar la fila y el asiento de cada QR. Si no la marcas, todas las entradas usan la misma fila y asiento.",
                )
            with st.container(key="qr_upload"):
                if generation_mode == "Una entrada":
                    qr_file = st.file_uploader("Arrastra una imagen aquí o selecciónala", type=["jpg", "jpeg", "png", "bmp"], key="qr_file", help="Formatos JPG, PNG, JPEG o BMP.", label_visibility="collapsed")
                    qr_files = [qr_file] if qr_file is not None else []
                elif seat_mode:
                    seat_count = int(st.number_input(
                        "Cantidad de entradas",
                        min_value=1,
                        max_value=MAX_SEAT_TICKETS,
                        value=2,
                        step=1,
                        key="seat_count",
                        help=f"Se crea una fila por entrada (máximo {MAX_SEAT_TICKETS}).",
                    ))
                    st.caption("Sube el QR de cada entrada y escribe su fila y asiento en la lista de abajo.")
                else:
                    qr_files = st.file_uploader(
                        "Arrastra varias imágenes aquí o selecciónalas",
                        type=["jpg", "jpeg", "png", "bmp"],
                        accept_multiple_files=True,
                        key="qr_files",
                        help="Puedes cargar hasta 20 fotografías JPG, PNG, JPEG o BMP.",
                        label_visibility="collapsed",
                    )
                    if len(qr_files) > 20:
                        st.warning("Se procesarán solamente las primeras 20 fotografías.", icon="⚠️")
                        qr_files = qr_files[:20]
            if qr_files:
                total_size = sum(len(item.getvalue()) for item in qr_files) / (1024 * 1024)
                label = qr_files[0].name if len(qr_files) == 1 else f"{len(qr_files)} fotografías seleccionadas"
                st.caption(f"{label} · {total_size:.2f} MB")

    if seat_mode:
        seen_qr_values: dict[str, str] = {}
        with st.container(border=True, key="seat_slots"):
            section_intro("Entradas con asiento", "Sube el QR de cada entrada e indica su fila y asiento.", "cyan", 3)
            summary_box = st.empty()
            for slot in range(1, seat_count + 1):
                with st.container(key=f"seat_slot_{slot}"):
                    badge_col, file_col, row_slot_col, seat_slot_col = st.columns([.5, 3, 1, 1], vertical_alignment="center")
                    badge_box = badge_col.empty()
                    with file_col:
                        uploaded_qr = st.file_uploader(
                            f"QR de la entrada {slot}",
                            type=["jpg", "jpeg", "png", "bmp"],
                            key=f"seat_qr_{slot}",
                            label_visibility="collapsed",
                        )
                    with row_slot_col:
                        slot_row = st.text_input(f"Fila {slot}", key=f"seat_row_{slot}", placeholder="Fila", max_chars=6, label_visibility="collapsed")
                    with seat_slot_col:
                        slot_seat = st.text_input(f"Asiento {slot}", key=f"seat_num_{slot}", placeholder="Asiento", max_chars=6, label_visibility="collapsed")
                    state, note = "empty", ""
                    if uploaded_qr is not None:
                        data = uploaded_qr.getvalue()
                        item = {
                            "name": f"Entrada {slot:02d}",
                            "key": qr_file_key(uploaded_qr.name, data),
                            "original": None, "result": None, "png": None, "error": None,
                            "row": slot_row, "seat": slot_seat,
                        }
                        try:
                            item["original"], item["result"] = digitalize_qr(data)
                            if item["result"].success and item["result"].validated:
                                qr_value = item["result"].validation_text
                                if qr_value in seen_qr_values:
                                    item["error"] = f"QR duplicado; ya fue cargado en {seen_qr_values[qr_value]}."
                                else:
                                    seen_qr_values[qr_value] = item["name"]
                                    item["png"] = encode_png(item["result"].clean)
                        except ValueError as error:
                            item["error"] = str(error)
                        qr_items.append(item)
                        if item["png"] is not None:
                            state = "ready" if slot_row.strip() and slot_seat.strip() else "pending"
                        else:
                            state = "error"
                            note = item["error"] or (item["result"].message if item["result"] is not None else "No se pudo validar el QR.")
                    badge_class = {"ready": " seat-badge--ok", "error": " seat-badge--bad"}.get(state, "")
                    badge_icon = {"ready": "✓", "error": "!"}.get(state, f"{slot:02d}")
                    badge_box.markdown(f'<div class="seat-badge{badge_class}">{badge_icon}</div>', unsafe_allow_html=True)
                    if note:
                        st.markdown(f'<div class="seat-note">{note}</div>', unsafe_allow_html=True)

            ready_items = [item for item in qr_items if item["png"] is not None]
            qr_ready = bool(ready_items)
            complete = sum(1 for item in ready_items if item["row"].strip() and item["seat"].strip())
            failed = len(qr_items) - len(ready_items)
            progress = round(100 * complete / seat_count) if seat_count else 0
            issues = f'<span class="seat-summary__bad">{failed} con error</span>' if failed else ""
            summary_box.markdown(
                f'<div class="seat-summary"><div class="seat-summary__top"><span><b class="seat-summary__ok">{complete}</b> de {seat_count} listas</span>{issues}</div>'
                f'<div class="seat-summary__bar"><span style="width:{progress}%"></span></div></div>',
                unsafe_allow_html=True,
            )

    elif qr_files:
        seen_qr_values: dict[str, str] = {}
        with st.spinner(f"Analizando y validando {len(qr_files)} código(s) QR…"):
            for uploaded_qr in qr_files:
                data = uploaded_qr.getvalue()
                item = {
                    "name": uploaded_qr.name,
                    "key": qr_file_key(uploaded_qr.name, data),
                    "original": None,
                    "result": None,
                    "png": None,
                    "error": None,
                }
                try:
                    item["original"], item["result"] = digitalize_qr(data)
                    if item["result"].success and item["result"].validated:
                        qr_value = item["result"].validation_text
                        if qr_value in seen_qr_values:
                            item["error"] = f"QR duplicado; ya fue cargado como {seen_qr_values[qr_value]}."
                        else:
                            seen_qr_values[qr_value] = uploaded_qr.name
                            item["png"] = encode_png(item["result"].clean)
                except ValueError as error:
                    item["error"] = str(error)
                qr_items.append(item)

        ready_items = [item for item in qr_items if item["png"] is not None]
        qr_ready = bool(ready_items)
        if generation_mode == "Una entrada" and ready_items:
            qr_original = ready_items[0]["original"]
            qr_result = ready_items[0]["result"]
            qr_png = ready_items[0]["png"]
        elif generation_mode == "Una entrada" and qr_items:
            qr_original = qr_items[0]["original"]
            qr_result = qr_items[0]["result"]
            qr_error = qr_items[0]["error"]

        with st.container(border=True, key="qr_result_card"):
            section_intro("Resultado del QR", "Comparación entre la fotografía y la matriz reconstruida.", "cyan", 3)
            if generation_mode == "Varias entradas":
                failed_count = len(qr_items) - len(ready_items)
                st.markdown(
                    f'<div class="batch-summary"><div class="batch-summary__item"><strong>{len(qr_items)}</strong><span>QR cargados</span></div><div class="batch-summary__item batch-summary__item--ok"><strong>{len(ready_items)}</strong><span>Listos para generar</span></div><div class="batch-summary__item batch-summary__item--error"><strong>{failed_count}</strong><span>Requieren revisión</span></div></div>',
                    unsafe_allow_html=True,
                )
                for index, item in enumerate(qr_items, start=1):
                    if item["png"] is not None:
                        st.success(f"{index:02d}. {item['name']} · QR reconstruido y validado", icon="✅")
                    else:
                        message = item["error"] or (item["result"].message if item["result"] is not None else "No se pudo validar el QR.")
                        st.error(f"{index:02d}. {item['name']} · {message}", icon="🚨")
                if failed_count:
                    st.caption("Los archivos que requieren revisión no se incluirán en el ZIP.")
            elif qr_error:
                st.error(qr_error, icon="🚨")
            elif qr_original is not None and qr_result is not None:
                original_column, arrow_column, result_column, status_column = st.columns([1.15, .25, 1.15, 1.6], vertical_alignment="center")
                with original_column:
                    st.caption("Imagen original")
                    st.image(cv2.cvtColor(qr_original, cv2.COLOR_BGR2RGB), width="stretch")
                with arrow_column:
                    st.markdown("<div style='text-align:center;color:#777f91;font-size:22px'>→</div>", unsafe_allow_html=True)
                with result_column:
                    st.caption("QR digitalizado")
                    if qr_result.success:
                        st.image(qr_result.clean, clamp=True, width="stretch")
                with status_column:
                    if qr_ready:
                        st.markdown(
                            """
                            <div class="qr-process">
                              <div class="qr-process__head">
                                <span class="qr-process__icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6 9 17l-5-5"/></svg></span>
                                <span><strong>Digitalización completada</strong><small>El código fue reconstruido y validado correctamente.</small></span>
                                <span class="qr-process__count">4/4</span>
                              </div>
                              <div class="qr-process__bar"><span></span></div>
                              <details class="qr-process__more"><summary>Ver pasos de validación</summary><div class="qr-process__steps">
                                <div class="qr-process__step"><span>✓</span><div><b>QR detectado</b><small>Patrón y límites localizados</small></div></div>
                                <div class="qr-process__step"><span>✓</span><div><b>Matriz reconstruida</b><small>Módulos convertidos a formato digital</small></div></div>
                                <div class="qr-process__step"><span>✓</span><div><b>Lectura validada</b><small>Contenido decodificado correctamente</small></div></div>
                                <div class="qr-process__step"><span>✓</span><div><b>Coincidencia confirmada</b><small>Original y resultado contienen el mismo código</small></div></div>
                              </div></details>
                              <div class="qr-process__approved"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/></svg> RESULTADO APROBADO PARA EL PDF</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                    elif qr_result.success:
                        st.warning(qr_result.message, icon="⚠️")
                    else:
                        st.error(f"No se pudo validar.\n\n{qr_result.message}", icon="🚨")

    detected = None
    pdf_info = None
    template_kind = None
    if pdf_data is not None:
        try:
            pdf_info = inspect_pdf(pdf_data)
            template_kind = detect_ticket_template(pdf_data)
            detected = inspect_ticket_fields(pdf_data)
            if pdf_source == "Plantilla Teleticket" and detected["category"].isdigit():
                detected["category"] = "PRE-VENTA IBK"
            elif pdf_source == "Plantilla Joinnus":
                detected.update(JOINNUS_SOUND_MUSIC_DEFAULTS)
                detected["purchase_date"] = ticket_identity["purchase_date"]
                detected["purchase_number"] = ticket_identity["purchase"]
                detected["transaction"] = ticket_identity["transaction"]
        except (ValueError, RuntimeError) as error:
            st.error(str(error), icon="🚨")

    if detected is not None:
        with st.container(border=True):
            section_intro("Información del evento", f"Documento compatible · {pdf_info['pages']} página(s)", "pink", 4)
            event_col, producer_col, ruc_col = st.columns([1.4, 1, .75])
            with event_col: event = st.text_input("Nombre del evento", detected["event"])
            with producer_col: producer = st.text_input("Productor", detected["producer"])
            with ruc_col: ruc = st.text_input("RUC", detected["ruc"], max_chars=11)
            producer_address = ""
            attendee_name = ""
            attendee_dni = ""
            transaction = ""
            purchase_date = ""
            purchase_number = ""
            if template_kind == "ticketmaster":
                producer_address = st.text_input(
                    "Dirección del productor",
                    detected.get("producer_address", ""),
                )
            elif template_kind == "joinnus":
                attendee_col, dni_col = st.columns([1.5, .7])
                with attendee_col:
                    attendee_name = st.text_input("Nombre del asistente", detected.get("attendee_name", ""))
                with dni_col:
                    attendee_dni = st.text_input("DNI", detected.get("attendee_dni", ""), max_chars=12)
            section_intro("Fecha y ubicación", "Información visible en la cabecera de la entrada.", "cyan", 5)
            day_col, date_col, time_col, location_col = st.columns([.7, .9, .8, 1.45])
            with day_col: day = st.text_input("Día", detected["day"])
            with date_col: date = st.text_input("Fecha", detected["date"])
            with time_col: time = st.text_input("Hora", detected["time"])
            with location_col: location = st.text_input("Lugar", detected["location"])
            address = ""
            if template_kind in {"ticketmaster", "joinnus"}:
                address = st.text_input("Dirección del recinto", detected.get("address", ""))
            section_intro("Información de la entrada", "Sector, ubicación asignada y precio.", "orange", 6)
            admission_type = ""
            door = ""
            service_charge = ""
            total_price = ""
            if template_kind == "ticketmaster":
                admission_col, sector_col, category_col, door_col = st.columns(4)
                with admission_col: admission_type = st.text_input("Tipo de entrada", detected.get("admission_type", ""))
                with sector_col: ticket_type = st.text_input("Sección", detected["ticket_type"])
                with category_col: category = st.text_input("Tarifa", detected["category"])
                with door_col: door = st.text_input("Puerta", detected.get("door", ""))
            else:
                sector_col, category_col = st.columns(2)
                with sector_col: ticket_type = st.text_input("Sector", detected["ticket_type"])
                with category_col: category = st.text_input("Categoría", detected["category"])
            row_col, seat_col, price_col = st.columns(3)
            with row_col: row = st.text_input("Fila", detected["row"], disabled=seat_mode, help="En modo asientos, la fila se indica en cada QR." if seat_mode else None)
            with seat_col: seat = st.text_input("Asiento", detected["seat"], disabled=seat_mode, help="En modo asientos, el asiento se indica en cada QR." if seat_mode else None)
            with price_col: price = st.text_input("Precio", detected["price"])
            if template_kind == "ticketmaster":
                service_col, total_col = st.columns(2)
                with service_col: service_charge = st.text_input("Cargo por servicio", detected.get("service_charge", ""))
                with total_col: total_price = st.text_input("Precio total", detected.get("total_price", ""))
            elif template_kind == "joinnus":
                purchase_col, transaction_col, purchase_date_col = st.columns([.75, 1.25, 1.15])
                with purchase_col:
                    purchase_number = st.text_input(
                        "Nro. de compra",
                        detected.get("purchase_number", ""),
                        key=f"joinnus_purchase_{ticket_identity['purchase']}",
                    )
                with transaction_col:
                    transaction = st.text_input(
                        "Transacción",
                        detected.get("transaction", ""),
                        key=f"joinnus_transaction_{ticket_identity['transaction']}",
                        disabled=True,
                        help="Se genera una transacción diferente para cada entrada digitalizada.",
                    )
                with purchase_date_col:
                    purchase_date = st.text_input(
                        "Fecha de compra",
                        detected.get("purchase_date", ""),
                        key=f"joinnus_purchase_date_{ticket_identity['purchase_date']}",
                        disabled=True,
                        help="Se asigna automáticamente la fecha y hora de emisión.",
                    )
            section_intro("Imagen del evento", "Reemplaza la fotografía o el logo de la plantilla.", "orange", 7)
            image_preview_col, image_control_col = st.columns([1, 2.2], vertical_alignment="center")
            with image_control_col:
                with st.container(key="event_image_upload"):
                    st.markdown('<div class="image-upload-marker"></div>', unsafe_allow_html=True)
                    event_image = st.file_uploader("Cambiar imagen", type=["png", "jpg", "jpeg", "webp"], key="event_image", help="Los PNG transparentes son ideales para logos.")
                    if template_kind == "ticketmaster":
                        image_mode_label = "Logo completo"
                        st.caption("La franja superior se rellena automáticamente y la portada principal se muestra completa.")
                    elif template_kind == "joinnus":
                        image_mode_label = "Rellenar espacio"
                        st.caption("La portada se adapta automáticamente a la miniatura del evento.")
                    else:
                        image_mode_label = st.segmented_control(
                            "Modo de imagen",
                            ["Logo completo", "Rellenar espacio"],
                            default="Logo completo",
                            width="stretch",
                        )
            with image_preview_col:
                if event_image is not None: st.image(event_image, caption="Imagen seleccionada", width="stretch")
                elif template_kind == "joinnus" and DEFAULT_JOINNUS_EVENT_IMAGE_PATH.exists():
                    st.image(
                        str(DEFAULT_JOINNUS_EVENT_IMAGE_PATH),
                        caption="Portada predeterminada de Sound Music Festival",
                        width="stretch",
                    )
                else: st.caption("Sin imagen nueva")

        if qr_ready:
            common_fields = {
                "event": event, "day": day, "date": date, "time": time,
                "location": location, "ticket_type": ticket_type, "row": row,
                "seat": seat, "category": category, "producer": producer,
                "ruc": ruc, "price": price, "address": address,
                "admission_type": admission_type, "door": door,
                "service_charge": service_charge, "total_price": total_price,
                "producer_address": producer_address,
                "attendee_name": attendee_name, "attendee_dni": attendee_dni,
                "transaction": transaction, "purchase_date": purchase_date,
                "purchase_number": purchase_number,
            }
            if event_image is not None:
                event_image_data = event_image.getvalue()
            elif template_kind == "joinnus" and DEFAULT_JOINNUS_EVENT_IMAGE_PATH.exists():
                event_image_data = DEFAULT_JOINNUS_EVENT_IMAGE_PATH.read_bytes()
            else:
                event_image_data = None
            image_mode = "cover" if image_mode_label == "Rellenar espacio" else "contain"
            if generation_mode == "Una entrada":
                try:
                    with st.spinner("Actualizando la vista previa…"):
                        fields = {
                            **common_fields,
                            "qr_number": ticket_identity["number"],
                            "qr_code": ticket_identity["code"],
                            "transaction": (
                                ticket_identity["transaction"]
                                if template_kind == "joinnus"
                                else transaction
                            ),
                            "purchase_date": (
                                ticket_identity["purchase_date"]
                                if template_kind == "joinnus"
                                else purchase_date
                            ),
                            "purchase_number": (
                                purchase_number
                                if template_kind == "joinnus" and purchase_number.strip()
                                else ticket_identity["purchase"]
                            ),
                            "ticket_number": ticket_identity["ticket"],
                        }
                        edited_pdf = build_ticket_pdf(pdf_data, fields, event_image_data, image_mode, qr_png)
                except (ValueError, RuntimeError) as error:
                    generation_error = str(error)
            else:
                with st.spinner(f"Generando {len(ready_items)} entrada(s) para el ZIP…"):
                    used_seats: dict[tuple[str, str], str] = {}
                    for item in ready_items:
                        identity = batch_ticket_identity(item["key"])
                        fields = {
                            **common_fields,
                            "qr_number": identity["number"],
                            "qr_code": identity["code"],
                            "transaction": (
                                identity["transaction"]
                                if template_kind == "joinnus"
                                else transaction
                            ),
                            "purchase_date": (
                                identity["purchase_date"]
                                if template_kind == "joinnus"
                                else purchase_date
                            ),
                            "purchase_number": identity["purchase"],
                            "ticket_number": identity["ticket"],
                        }
                        if seat_mode:
                            item_row = item.get("row", "").strip()
                            item_seat = item.get("seat", "").strip()
                            if not item_row or not item_seat:
                                batch_generation_errors.append(f"{item['name']}: falta indicar la fila y el asiento.")
                                continue
                            if (item_row, item_seat) in used_seats:
                                batch_generation_errors.append(
                                    f"{item['name']}: la fila {item_row} y el asiento {item_seat} ya se usaron en {used_seats[(item_row, item_seat)]}."
                                )
                                continue
                            used_seats[(item_row, item_seat)] = item["name"]
                            fields["row"] = item_row
                            fields["seat"] = item_seat
                            batch_seat_labels[item["key"]] = f"-Asiento-{safe_filename_stem(item_seat, 'x')}-Fila-{safe_filename_stem(item_row, 'x')}"
                        try:
                            generated_pdf = build_ticket_pdf(pdf_data, fields, event_image_data, image_mode, item["png"])
                            batch_entries.append((item["key"], generated_pdf))
                        except (ValueError, RuntimeError) as error:
                            batch_generation_errors.append(f"{item['name']}: {error}")
                if batch_entries:
                    edited_pdf = batch_entries[0][1]

with preview_column:
    with st.container(border=True, key="preview_card"):
        st.markdown('<div class="preview-marker card-accent card-accent--preview"></div>', unsafe_allow_html=True)
        section_intro("Vista previa de la entrada", "Así se verá el documento con la información actualizada.", "orange", 8)
        render_pdf_preview(edited_pdf or pdf_data)
        if generation_error:
            st.error(generation_error, icon="🚨")
        elif generation_mode == "Varias entradas" and batch_entries:
            base_name = st.text_input(
                "Nombre base de los PDF",
                value="E-ticket",
                key=f"batch_download_name_{pdf_name}",
                help="Los archivos se numerarán automáticamente: nombre-001.pdf, nombre-002.pdf…",
            )
            safe_base = safe_filename_stem(base_name)
            numbered_entries = [
                (f"{safe_base}-{index:03d}{batch_seat_labels.get(entry_key, '')}.pdf", pdf_bytes)
                for index, (entry_key, pdf_bytes) in enumerate(batch_entries, start=1)
            ]
            zip_data = build_ticket_zip(numbered_entries)
            st.caption(f"El ZIP contiene {len(numbered_entries)} PDF independientes. La vista previa corresponde a la primera entrada.")
            if batch_generation_errors:
                st.warning(
                    f"{len(batch_generation_errors)} entrada(s) no se incluyeron en el ZIP:\n\n"
                    + "\n".join(f"- {message}" for message in batch_generation_errors),
                    icon="⚠️",
                )
            if st.button(
                f"Digitalizar {len(numbered_entries)} entradas",
                type="primary",
                icon=":material/auto_fix_high:",
                width="stretch",
                key=f"open_batch_result_{safe_base}",
            ):
                complete_download(len(numbered_entries), "batch")
                show_generation_dialog(
                    entry_names=[filename for filename, _ in numbered_entries],
                    download_data=zip_data,
                    download_filename=f"{safe_base}.zip",
                    download_mime="application/zip",
                    mode="batch",
                    event_name=event,
                    source_name=pdf_source,
                    errors=batch_generation_errors,
                )
            st.caption("Cada PDF conserva el QR reconstruido correspondiente y utiliza identificadores únicos.")
        elif edited_pdf is not None:
            download_name = st.text_input(
                "Nombre del PDF",
                value=default_ticket_name(row, seat),
                key=f"download_name_{pdf_name}",
                help="Puedes escribir el nombre con o sin la extensión .pdf.",
            )
            st.caption(f"Identificadores de esta descarga: N° {ticket_identity['number']} · {ticket_identity['code']}")
            single_filename = safe_pdf_filename(download_name)
            if st.button(
                "Digitalizar entrada",
                type="primary",
                icon=":material/auto_fix_high:",
                width="stretch",
                key=f"open_single_result_{single_filename}",
            ):
                complete_download(1, "single")
                show_generation_dialog(
                    entry_names=[single_filename],
                    download_data=edited_pdf,
                    download_filename=single_filename,
                    download_mime="application/pdf",
                    mode="single",
                    event_name=event,
                    source_name=pdf_source,
                )
            st.caption("Se generará un nuevo PDF sin modificar el archivo original.")
        else:
            disabled_label = "Descargar entradas en ZIP" if generation_mode == "Varias entradas" else "Descargar entrada digitalizada"
            if batch_generation_errors:
                st.warning(
                    "No se generó ninguna entrada:\n\n" + "\n".join(f"- {message}" for message in batch_generation_errors),
                    icon="⚠️",
                )
            st.button(disabled_label, disabled=True, icon=":material/download:", width="stretch")
            st.caption("Selecciona el PDF y valida al menos un QR para habilitar la descarga.")
