"""Conservative model catalog. Product IDs are data, not an authentication boundary."""
from dataclasses import dataclass
import re

@dataclass(frozen=True)
class Model:
    key: str
    name: str
    chip: str
    image: str
    products: tuple = ()

MODELS = (
    Model('airpods2', 'AirPods 2', 'H1', 'airpods2.png', (0x200f,)),
    Model('airpods3', 'AirPods 3', 'H1', 'airpods3.png', (0x2013,)),
    Model('airpods4', 'AirPods 4', 'H2', 'airpods4.png', (0x2019, 0x201b)),
    Model('airpodspro', 'AirPods Pro', 'H1', 'airpodspro.png', (0x200e,)),
    Model('airpodspro2', 'AirPods Pro 2', 'H2', 'airpodspro2.png', (0x2014, 0x2024)),
    Model('airpodsmax', 'AirPods Max', 'H1', 'airpodsmax.png', (0x200a, 0x201f)),
    Model('beatsfitpro', 'Beats Fit Pro', 'H1', 'beatsfitpro.png', (0x2012,)),
    Model('powerbeatsfit', 'Powerbeats Fit', 'H1', 'powerbeatsfit.png'),
    Model('powerbeatspro', 'Powerbeats Pro', 'H1', 'powerbeatspro.png', (0x200b,)),
    Model('powerbeatspro2', 'Powerbeats Pro 2', 'H2', 'powerbeatspro2.png', (0x201d,)),
    Model('solopro', 'Beats Solo Pro', 'H1', 'solopro.png', (0x200c,)),
)
BY_KEY = {m.key: m for m in MODELS}
BY_PRODUCT = {pid: m for m in MODELS for pid in m.products}
UNSUPPORTED_PRODUCTS = {0x2002, 0x2003, 0x2005, 0x2006, 0x2010, 0x2011, 0x2016, 0x2017, 0x2025, 0x2026}
MAC = re.compile(r'^[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}$')

def valid_mac(value):
    return isinstance(value, str) and bool(MAC.fullmatch(value))

def product_id(props):
    """Prefer classic SDP Device ID, then Apple proximity data on this same object.

    Do not correlate randomized BLE addresses with paired classic devices by name.
    """
    modalias = props.get('Modalias', '')
    match = re.fullmatch(r'bluetooth:v004Cp([0-9A-Fa-f]{4})d[0-9A-Fa-f]{4}', modalias, re.I)
    if match:
        return int(match[1], 16)
    payload = props.get('ManufacturerData', {}).get(0x004c, b'')
    if hasattr(payload, 'unpack'):
        payload = payload.unpack()
    payload = bytes(payload)
    if len(payload) >= 5 and payload[:2] == b'\x07\x19':
        return int.from_bytes(payload[3:5], 'little')
    return None

def identify(props):
    pid = product_id(props)
    if pid in UNSUPPORTED_PRODUCTS:
        return None, 'unsupported'
    if pid in BY_PRODUCT:
        return BY_PRODUCT[pid], 'detected'
    name = (props.get('Name', '') + ' ' + props.get('Alias', '')).lower()
    if any(n in name for n in ('studio buds', 'studio pro', 'studio3', 'studio 3', 'solo buds', 'solo 4', 'solo4', 'solo3', 'solo 3', 'beats flex', 'beatsx', 'powerbeats3', 'powerbeats 3')):
        return None, 'unsupported'
    # Unknown identifiers are not silently overridden using a friendly name.
    if pid is not None:
        return None, 'unknown'
    for model in sorted(MODELS, key=lambda m: len(m.name), reverse=True):
        if model.name.lower() in name:
            return model, 'confirm'
    return None, 'unknown'
