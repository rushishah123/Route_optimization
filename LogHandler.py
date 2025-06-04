import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
import sys
from elasticsearch import Elasticsearch
from logging import Handler
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

class ElasticsearchLogHandler(Handler):
    def __init__(self, es_host, es_port, index, username=None, password=None, scheme="http"):
        super().__init__()
        # Elasticsearch connection config
        self.es_config = {
            "hosts": [f"{scheme}://{es_host}:{es_port}"],
            "verify_certs": False,  
            "ssl_show_warn": False
        }
        if username and password:
            self.es_config["basic_auth"] = (username, password)
        try:
            self.es = Elasticsearch(**self.es_config)
            if not self.es.ping():
                raise ValueError("Failed to connect to Elasticsearch")
            self.index = index
            print(f"Connected to Elasticsearch at {es_host}")
            # Ensure the index exists
            self.create_index()
        except Exception as e:
            print(f"Elasticsearch connection error: {e}")
            self.es = None

    def create_index(self):
        if not self.es.indices.exists(index=self.index):
            mappings = {
                "mappings": {
                    "properties": {
                        "@timestamp": {"type": "date"},
                        "message": {"type": "text"}
                    }
                }
            }
            self.es.indices.create(index=self.index, body=mappings)
            print(f"Created index: {self.index}")

    def emit(self, record):
        """Send log record to Elasticsearch."""
        if not self.es:
            print("Elasticsearch connection is not available.")
            return
        log_entry = self.format(record)
        try:
            self.es.index(index=self.index, document=log_entry)
        except Exception as e:
            print(f"Failed to log to Elasticsearch: {e}")

    def format(self, record):
        """Format the log record as a JSON document."""
        return {
            "@timestamp": datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
            "message": record.getMessage()
        }

class LogHandler:
    """
    A custom log handler that saves logs both to files and Elasticsearch/Kibana.
    Features:
    - Creates logs directory if it doesn't exist
    - Rotating file handler to prevent huge log files
    - Console output for development
    - Elasticsearch/Kibana integration
    - Different log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    
    def __init__(
        self,
        log_dir="logs",
        log_file_prefix="app",
        max_bytes=5_000_000,  # 5MB
        backup_count=5,
        log_level=logging.INFO,
        console_output=True,
        es_config=None  # Optional Elasticsearch configuration
    ):
        self.log_dir = log_dir
        self.log_file_prefix = log_file_prefix
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.log_level = log_level
        self.console_output = console_output
        
        # Create logger
        self.logger = logging.getLogger(self.log_file_prefix)
        self.logger.setLevel(self.log_level)
        
        # Create logs directory if it doesn't exist
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
        
        # Set up log formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%dT%H:%M:%S%z'
        )
        
        # Set up file handler with rotation
        log_file = os.path.join(
            self.log_dir,
            f"{self.log_file_prefix}_{datetime.now().strftime('%Y%m%d')}.log"
        )
        
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=self.max_bytes,
            backupCount=self.backup_count
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        
        # Add console handler if requested
        if self.console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

        # Add Elasticsearch handler if config is provided
        if es_config:
            es_handler = ElasticsearchLogHandler(**es_config)
            self.logger.addHandler(es_handler)
    
    def get_logger(self):
        """Returns the configured logger instance."""
        return self.logger

def setup_logger(
    log_dir="logs",
    log_file_prefix="app",
    log_level=logging.INFO,
    console_output=True,
    es_config=None
):
    """
    Helper function to quickly set up a logger with default settings.
    Returns a configured logger instance.
    """
    handler = LogHandler(
        log_dir=log_dir,
        log_file_prefix=log_file_prefix,
        log_level=log_level,
        console_output=console_output,
        es_config=es_config
    )
    return handler.get_logger()

# Usage example
if __name__ == "__main__":
    # Example Elasticsearch configuration
    es_config = {
        "es_host": "localhost",
        "es_port": 9200,
        "index": "my-application-logs"
    }
    
    # Setup logger with both file and Elasticsearch logging
    logger = setup_logger(
        log_file_prefix="example",
        es_config=es_config
    )
    
    # Log some messages
    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")
    logger.critical("This is a critical message")
