import os
import logging
import sys

# Configure core logging framework to stream out to stdout/stderr
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] Tenant=%(processName)s File=%(filename)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("carrier-routing-tier")

def process_carrier_stream():
    # Read the container environment injections we mapped out in k8s/TF
    carrier = os.getenv("CARRIER_NAME", "unknown-carrier")
    lob = os.getenv("LINE_OF_BUSINESS", "unknown-lob")
    bucket = os.getenv("AWS_S3_BUCKET", "unknown-bucket")
    
    logger.info(f"Booting application context for {carrier} ({lob} line). Binding to cloud bucket: {bucket}")
    
    # Mock routing sequence
    try:
        # If your app tries to handle an unencrypted file or data leak, trigger an alert
        if bucket == "unknown-bucket":
            raise ValueError("HIPAA Violation Warning: Attempted to process protected health information without an explicit target S3 Bucket!")
        
        logger.info(f"Successfully processed batch data lifecycle for tenant: {carrier}")
        
    except Exception as e:
        # CRITICAL: This exact string pattern 'ERROR' trips your CloudWatch metric filter alarm!
        logger.error(f"[ERROR] Critical transaction failure in {carrier}-{lob} stack. Details: {str(e)}")

if __name__ == "__main__":
    process_carrier_stream()
