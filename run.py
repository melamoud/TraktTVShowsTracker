"""
TraktTV Shows Tracker - server runner (HTTPS, optional scheduler).

Usage:
    python run.py
    python run.py --no-scheduler
    python run.py --http          # local debug without TLS (set SESSION_COOKIE_SECURE=0)
"""

import argparse
import os
import ssl
import sys

from app import app
from config import Config


def build_ssl_context():
    """Load TLS cert/key and require TLS 1.2+."""
    cert_file = app.config.get('SSL_CERT_FILE', 'cert.pem')
    key_file = app.config.get('SSL_KEY_FILE', 'key.pem')
    if not os.path.isfile(cert_file) or not os.path.isfile(key_file):
        raise SystemExit(
            f"Missing TLS files '{cert_file}' / '{key_file}'. "
            f"Run: python generate_cert.py"
        )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert_file, key_file)
    return context


def write_pid():
    """Write server PID for stop scripts."""
    pid_file = app.config.get('PID_FILE') or '.server.pid'
    with open(pid_file, 'w', encoding='utf-8') as fh:
        fh.write(str(os.getpid()))


def clear_pid():
    """Remove PID file if it belongs to this process."""
    pid_file = app.config.get('PID_FILE') or '.server.pid'
    try:
        if os.path.isfile(pid_file):
            os.remove(pid_file)
    except OSError:
        pass


def main():
    """Parse CLI flags and start the Flask server."""
    parser = argparse.ArgumentParser(description='Run TraktTV Shows Tracker')
    parser.add_argument('--no-scheduler', action='store_true', help='Disable background sync jobs')
    parser.add_argument('--http', action='store_true', help='Run plain HTTP (dev only)')
    args = parser.parse_args()

    scheduler = None
    if not args.no_scheduler:
        try:
            from services.sync_jobs import start_scheduler
            scheduler = start_scheduler(app)
        except Exception as exc:
            app.logger.warning('Scheduler not started: %s', exc)

    write_pid()
    host = app.config.get('HOST', '0.0.0.0')
    port = int(app.config.get('PORT', 8300))
    debug = bool(app.config.get('DEBUG', True))

    try:
        if args.http:
            print(f'Starting HTTP on http://{host}:{port} (dev only)')
            app.run(host=host, port=port, debug=debug, use_reloader=False)
        else:
            context = build_ssl_context()
            print(f'Starting HTTPS on https://{host}:{port}')
            print(f'Public host target: {app.config.get("PUBLIC_HOST")}')
            app.run(host=host, port=port, debug=debug, ssl_context=context, use_reloader=False)
    finally:
        if scheduler:
            scheduler.shutdown(wait=False)
        clear_pid()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        clear_pid()
        sys.exit(0)
