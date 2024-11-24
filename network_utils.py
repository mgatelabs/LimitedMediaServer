import socket
import ipaddress

def get_local_ip():
    try:
        # Connect to a remote server to determine the IP (no actual data is sent)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip_address = s.getsockname()[0]
        return ip_address
    except Exception as e:
        print(f"Error getting local IP: {e}")
        return None

def is_private_ip(ip):
    try:
        ip_obj = ipaddress.ip_address(ip)
        return ip_obj.is_private
    except ValueError:
        print(f"Invalid IP address: {ip}")
        return False