#!/usr/bin/env python3
"""
OPSEC Proxy Server - Simple HTTP/HTTPS Proxy
"""

import socket
import threading
import os
import sys
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
PORT = int(os.environ.get('PORT', 8080))
BUFFER_SIZE = 8192

def handle_client(client_socket, address):
    """Handle each client connection"""
    logger.info(f"Connection from {address[0]}:{address[1]}")
    
    try:
        # Receive initial request
        client_socket.settimeout(10)
        request_data = b''
        
        while True:
            try:
                chunk = client_socket.recv(BUFFER_SIZE)
                if not chunk:
                    break
                request_data += chunk
                # Check if we have complete headers or CONNECT request
                if b'\r\n\r\n' in request_data or request_data.startswith(b'CONNECT'):
                    break
            except socket.timeout:
                break
        
        if not request_data:
            client_socket.close()
            return
        
        # Handle CONNECT method (HTTPS)
        if request_data.startswith(b'CONNECT'):
            # Parse CONNECT host:port HTTP/1.1
            first_line = request_data.split(b'\r\n')[0].decode('utf-8', errors='ignore')
            parts = first_line.split()
            if len(parts) >= 2:
                host_port = parts[1]
                if ':' in host_port:
                    host, port_str = host_port.split(':')
                    port = int(port_str)
                    handle_connect(client_socket, host, port)
                else:
                    client_socket.close()
        else:
            # Handle regular HTTP request
            handle_http(client_socket, request_data)
            
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        client_socket.close()

def handle_http(client_socket, request_data):
    """Handle regular HTTP requests"""
    try:
        # Parse the request to get the host
        request_str = request_data.decode('utf-8', errors='ignore')
        lines = request_str.split('\r\n')
        
        host = None
        port = 80
        
        # Find the Host header
        for line in lines:
            if line.lower().startswith('host:'):
                host_part = line[5:].strip()
                if ':' in host_part:
                    host, port_str = host_part.split(':')
                    port = int(port_str)
                else:
                    host = host_part
                break
        
        if not host:
            error_response = b'HTTP/1.1 400 Bad Request\r\n\r\n'
            client_socket.send(error_response)
            return
        
        logger.info(f"HTTP request to {host}:{port}")
        
        # Connect to target server
        target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        target_socket.settimeout(30)
        target_socket.connect((host, port))
        
        # Forward the request
        target_socket.send(request_data)
        
        # Get and forward response
        while True:
            response = target_socket.recv(BUFFER_SIZE)
            if not response:
                break
            client_socket.send(response)
        
        target_socket.close()
        
    except Exception as e:
        logger.error(f"HTTP error: {e}")
        try:
            error_response = b'HTTP/1.1 502 Bad Gateway\r\n\r\n'
            client_socket.send(error_response)
        except:
            pass

def handle_connect(client_socket, host, port):
    """Handle HTTPS CONNECT tunnel"""
    try:
        logger.info(f"CONNECT tunnel to {host}:{port}")
        
        # Connect to target server
        target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        target_socket.settimeout(30)
        target_socket.connect((host, port))
        
        # Send 200 Connection Established
        client_socket.send(b'HTTP/1.1 200 Connection Established\r\n\r\n')
        
        # Start bidirectional forwarding
        def forward(source, dest):
            try:
                while True:
                    data = source.recv(BUFFER_SIZE)
                    if not data:
                        break
                    dest.send(data)
            except:
                pass
            finally:
                try:
                    source.close()
                except:
                    pass
                try:
                    dest.close()
                except:
                    pass
        
        # Create threads for both directions
        thread_client_to_target = threading.Thread(target=forward, args=(client_socket, target_socket))
        thread_target_to_client = threading.Thread(target=forward, args=(target_socket, client_socket))
        
        thread_client_to_target.daemon = True
        thread_target_to_client.daemon = True
        
        thread_client_to_target.start()
        thread_target_to_client.start()
        
        # Wait for either thread to finish
        thread_client_to_target.join()
        thread_target_to_client.join()
        
    except Exception as e:
        logger.error(f"CONNECT error: {e}")
        try:
            client_socket.send(b'HTTP/1.1 502 Bad Gateway\r\n\r\n')
        except:
            pass

def start_server():
    """Start the proxy server"""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('0.0.0.0', PORT))
    server_socket.listen(50)
    
    print(f"""
    ╔══════════════════════════════════════════╗
    ║     OPSEC Proxy Server v1.0              ║
    ║     Running on port {PORT}                    ║
    ╚══════════════════════════════════════════╝
    """)
    
    logger.info(f"Proxy server listening on port {PORT}")
    logger.info(f"Configure your browser to use: http://localhost:{PORT}")
    
    try:
        while True:
            client_socket, address = server_socket.accept()
            thread = threading.Thread(target=handle_client, args=(client_socket, address))
            thread.daemon = True
            thread.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        server_socket.close()

if __name__ == '__main__':
    start_server()
