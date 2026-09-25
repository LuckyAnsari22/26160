import logging
import json
import logging.handlers
from datetime import datetime
import os

os.makedirs("logs", exist_ok=True)

class SIEMJSONFormatter(logging.Formatter):
    """Formats log records as MITRE ATT&CK tagged JSON for SIEM ingestion."""
    def format(self, record):
        log_obj = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "source": "Antigravity-IPsec-Sensor",
            "level": record.levelname,
            "message": record.getMessage(),
            "event_type": getattr(record, "event_type", "audit"),
            "mitre_tactics": getattr(record, "mitre_tactics", []),
            "mitre_techniques": getattr(record, "mitre_techniques", []),
            "severity_score": getattr(record, "severity_score", 0),
            "flow_id": getattr(record, "flow_id", "unknown")
        }
        return json.dumps(log_obj)

def get_siem_logger():
    logger = logging.getLogger("SIEM_Emitter")
    logger.setLevel(logging.INFO)
    
    # Avoid duplicate handlers if called multiple times
    if not logger.handlers:
        # File handler to simulate syslog destination
        fh = logging.FileHandler("logs/siem_syslog.jsonl")
        fh.setFormatter(SIEMJSONFormatter())
        logger.addHandler(fh)
        
        # Real syslog handler (commented out for local Windows dev, but structured ready)
        # syslog_handler = logging.handlers.SysLogHandler(address=('localhost', 514))
        # syslog_handler.setFormatter(SIEMJSONFormatter())
        # logger.addHandler(syslog_handler)
        
    return logger

siem_logger = get_siem_logger()

def emit_alert(message: str, event_type: str, severity: int, flow_id: str, mitre_tactics: list, mitre_techniques: list):
    """Helper to emit structured JSON-over-Syslog"""
    siem_logger.info(
        message, 
        extra={
            "event_type": event_type,
            "severity_score": severity,
            "flow_id": flow_id,
            "mitre_tactics": mitre_tactics,
            "mitre_techniques": mitre_techniques
        }
    )
