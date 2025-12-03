# evv_service.py
import requests
import logging
from django.conf import settings
import json
import time

logger = logging.getLogger(__name__)


class EVVService:
    def __init__(self):
        self.base_url = settings.EVV_API_BASE
        self.subscription_key = settings.EVV_SUBSCRIPTION_KEY
        self.account_id = getattr(settings, 'EVV_ACCOUNT_ID', None)
        self.provider_id = getattr(settings, 'EVV_PROVIDER_ID', None)

    def _get_headers(self):
        return {
            "Cache-Control": "no-cache",
            "Ocp-Apim-Subscription-Key": self.subscription_key,
            "Content-Type": "application/json",
            "Account": self.account_id
        }
    
    def get_upload_status(self, transaction_id):
        """Check the status of a previous upload"""
        # Try different parameter names that EVV might expect
        param_variations = [
            {"id": transaction_id},
            {"uuid": transaction_id},
            {"transactionId": transaction_id},
            {"transactionID": transaction_id},
            {"uploadId": transaction_id},
        ]
        
        for params in param_variations:
            result = self.send("/clients/status", "GET", params=params)
            if result["status_code"] == 200:
                return result
        
        # If none worked, try the direct endpoint as fallback
        url = f"{self.base_url}/clients/upload/{transaction_id}"
        headers = self._get_headers()
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            
            return {
                "status_code": response.status_code,
                "response": response.json() if response.content else {},
                "url": url,
                "method": "GET",
                "transaction_id": transaction_id
            }
        except Exception as e:
            logger.error(f"Error checking upload status for {transaction_id}: {str(e)}")
            # Return the last attempted result from param variations
            return result if 'result' in locals() else {
                "status_code": 500,
                "response": {"error": "Request failed", "message": str(e)},
                "url": url,
                "method": "GET",
                "transaction_id": transaction_id
            }

    def send(self, path, method="GET", payload=None, params=None):
        url = f"{self.base_url}{path}"
        headers = self._get_headers()
        
        logger.info(f"EVV API Request: {method} {url}")
        if params:
            logger.info(f"Query params: {params}")
        
        # Log the payload for debugging
        if payload is not None:
            logger.info(f"Payload type: {type(payload)}")
            logger.info(f"Payload: {json.dumps(payload, indent=2)[:1000]}...")

        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, params=params, timeout=30)
            else:
                response = requests.post(url, json=payload, headers=headers, params=params, timeout=30)

            logger.info(f"EVV API Response Status: {response.status_code}")
            
            response_data = self._safe_parse_response(response)
            
            return {
                "status_code": response.status_code,
                "response": response_data,
                "url": url,
                "method": method,
                "params_used": params,
                "account_id_used": self.account_id,
                "provider_id_used": self.provider_id
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"EVV API request exception: {e}")
            return {
                "status_code": 500,
                "response": {"error": "Request failed", "message": str(e)},
                "url": url,
                "method": method,
                "params_used": params
            }

    def _safe_parse_response(self, response):
        if not response.content:
            return {"message": "Empty response received"}

        try:
            return response.json()
        except ValueError:
            return {
                "error": "Invalid JSON response",
                "status_code": response.status_code,
                "content_preview": response.text[:500],
            }

    def upload_clients(self, data):
        """
        Upload clients to EVV - handles both array and dictionary payloads
        """
        try:
            logger.info(f"upload_clients received data type: {type(data)}")
            
            # If data is a list (array from frontend), use it directly
            if isinstance(data, list):
                logger.info(f"Received list with {len(data)} clients")
                payload = data
            # If data is a dict with Clients key, extract the list
            elif isinstance(data, dict) and 'Clients' in data:
                logger.info("Received dict with Clients key")
                payload = data['Clients']
            # If data is a dict without Clients key, try to use it as-is
            elif isinstance(data, dict):
                logger.info("Received dict without Clients key, using as-is")
                payload = data
            else:
                return {
                    "status_code": 400,
                    "response": {"error": "Invalid payload format", "message": "Payload must be a list or dictionary"},
                    "url": f"{self.base_url}/clients/upload",
                    "method": "POST"
                }
            
            # Send the payload to EVV API
            return self.send("/clients/upload", "POST", payload)
            
        except Exception as e:
            logger.error(f"Error in upload_clients: {str(e)}")
            logger.error(f"Error details: {repr(e)}")
            return {
                "status_code": 500,
                "response": {"error": "Internal server error", "message": str(e)},
                "url": f"{self.base_url}/clients/upload",
                "method": "POST"
            }

    def upload_employees(self, data):
        """
        Upload employees to EVV - handles both array and dictionary payloads
        """
        try:
            logger.info(f"upload_employees received data type: {type(data)}")
            
            # If data is a list (array from frontend), use it directly
            if isinstance(data, list):
                logger.info(f"Received list with {len(data)} employees")
                payload = data
            # If data is a dict with Employees key, extract the list
            elif isinstance(data, dict) and 'Employees' in data:
                logger.info("Received dict with Employees key")
                payload = data['Employees']
            # If data is a dict without Employees key, try to use it as-is
            elif isinstance(data, dict):
                logger.info("Received dict without Employees key, using as-is")
                payload = data
            else:
                return {
                    "status_code": 400,
                    "response": {"error": "Invalid payload format", "message": "Payload must be a list or dictionary"},
                    "url": f"{self.base_url}/employees/upload",
                    "method": "POST"
                }
            
            # Send the payload to EVV API
            return self.send("/employees/upload", "POST", payload)
            
        except Exception as e:
            logger.error(f"Error in upload_employees: {str(e)}")
            logger.error(f"Error details: {repr(e)}")
            return {
                "status_code": 500,
                "response": {"error": "Internal server error", "message": str(e)},
                "url": f"{self.base_url}/employees/upload",
                "method": "POST"
            }

    def upload_xrefs(self, data):
        """
        Upload xrefs to EVV - handles both array and dictionary payloads
        """
        try:
            logger.info(f"upload_xrefs received data type: {type(data)}")
            
            if isinstance(data, list):
                logger.info(f"Received list with {len(data)} xrefs")
                payload = data
            elif isinstance(data, dict) and 'Xrefs' in data:
                logger.info("Received dict with Xrefs key")
                payload = data['Xrefs']
            elif isinstance(data, dict):
                logger.info("Received dict without Xrefs key, using as-is")
                payload = data
            else:
                return {
                    "status_code": 400,
                    "response": {"error": "Invalid payload format", "message": "Payload must be a list or dictionary"},
                    "url": f"{self.base_url}/xrefs/upload",
                    "method": "POST"
                }
            
            return self.send("/xrefs/upload", "POST", payload)
            
        except Exception as e:
            logger.error(f"Error in upload_xrefs: {str(e)}")
            return {
                "status_code": 500,
                "response": {"error": "Internal server error", "message": str(e)},
                "url": f"{self.base_url}/xrefs/upload",
                "method": "POST"
            }

    def upload_visits(self, data):
        """
        Upload visits to EVV - handles both array and dictionary payloads
        """
        try:
            logger.info(f"upload_visits received data type: {type(data)}")
            
            if isinstance(data, list):
                logger.info(f"Received list with {len(data)} visits")
                payload = data
            elif isinstance(data, dict) and 'Visits' in data:
                logger.info("Received dict with Visits key")
                payload = data['Visits']
            elif isinstance(data, dict):
                logger.info("Received dict without Visits key, using as-is")
                payload = data
            else:
                return {
                    "status_code": 400,
                    "response": {"error": "Invalid payload format", "message": "Payload must be a list or dictionary"},
                    "url": f"{self.base_url}/visits/upload",
                    "method": "POST"
                }
            
            return self.send("/visits/upload", "POST", payload)
            
        except Exception as e:
            logger.error(f"Error in upload_visits: {str(e)}")
            return {
                "status_code": 500,
                "response": {"error": "Internal server error", "message": str(e)},
                "url": f"{self.base_url}/visits/upload",
                "method": "POST"
            }

    def get_account(self):
        return self.send("/management/account-id", "GET")

    def get_status(self, entity, transaction_id=None):
        """Get status for clients, visits, employees, claims, etc."""
        if transaction_id:
            # For individual transaction status, use as query parameter
            return self.send(f"/{entity}/status", "GET", params={"id": transaction_id})
        else:
            # For general entity status
            return self.send(f"/{entity}/status", "GET")
        
    