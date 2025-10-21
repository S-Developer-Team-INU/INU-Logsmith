from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import json


@dataclass
class UserIdentity:
    type: str
    principal_id: str
    arn: str
    account_id: str
    access_key_id: Optional[str] = None
    user_name: Optional[str] = None
    session_context: Optional[Dict[str, Any]] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserIdentity':
        return cls(
            type=data.get('type', ''),
            principal_id=data.get('principalId', ''),
            arn=data.get('arn', ''),
            account_id=data.get('accountId', ''),
            access_key_id=data.get('accessKeyId'),
            user_name=data.get('userName'),
            session_context=data.get('sessionContext')
        )


@dataclass
class TlsDetails:
    tls_version: str
    cipher_suite: str
    client_provided_host_header: str
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TlsDetails':
        return cls(
            tls_version=data.get('tlsVersion', ''),
            cipher_suite=data.get('cipherSuite', ''),
            client_provided_host_header=data.get('clientProvidedHostHeader', '')
        )


@dataclass
class CloudTrailEvent:
    event_id: str
    event_version: str
    event_time: str
    event_source: str
    event_name: str
    event_category: str
    event_type: str
    aws_region: str
    read_only: bool
    request_id: str
    source_ip_address: str
    user_agent: str
    management_event: bool
    recipient_account_id: str
    user_identity: UserIdentity
    request_parameters: Dict[str, Any]
    response_elements: Dict[str, Any]
    session_credential_from_console: Optional[str] = None
    shared_event_id: str = None
    error_code: str = None
    error_message: str = None
    tls_details: Optional[TlsDetails] = None
    insight_details: Dict[str, Any] = None
    resources: Dict[str, Any] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CloudTrailEvent':
        user_identity = UserIdentity.from_dict(data.get('userIdentity', {}))
        
        tls_details = None
        if 'tlsDetails' in data:
            tls_details = TlsDetails.from_dict(data['tlsDetails'])
        
        return cls(
            event_id=data.get('eventID', ''),
            event_version=data.get('eventVersion', ''),
            event_time=data.get('eventTime', ''),
            event_source=data.get('eventSource', ''),
            event_name=data.get('eventName', ''),
            event_category=data.get('eventCategory', ''),
            event_type=data.get('eventType', ''),
            aws_region=data.get('awsRegion', ''),
            read_only=data.get('readOnly', False),
            request_id=data.get('requestID', ''),
            source_ip_address=data.get('sourceIPAddress', ''),
            user_agent=data.get('userAgent', ''),
            management_event=data.get('managementEvent', False),
            recipient_account_id=data.get('recipientAccountId', ''),
            session_credential_from_console=data.get('sessionCredentialFromConsole'),
            shared_event_id=data.get('sharedEventId'),
            error_code=data.get('errorCode'),
            error_message=data.get('errorMessage'),
            user_identity=user_identity,
            tls_details=tls_details,
            request_parameters=data.get('requestParameters', {}),
            response_elements=data.get('responseElements', {}),
            insight_details=data.get('insightDetails'),
            resources=data.get('resources')
        )


@dataclass
class CloudTrailLogData:
    records: List[CloudTrailEvent]
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CloudTrailLogData':
        events = [
            CloudTrailEvent.from_dict(record) 
            for record in data.get('Records', [])
        ]
        
        return cls(records=events)
    
    @property
    def total_events(self) -> int:
        return len(self.records)


class CloudTrailCollector:
    def load_from_json(self, file_path: str) -> CloudTrailLogData:
        with open(file_path, 'r') as f:
            data = json.load(f)
        return CloudTrailLogData.from_dict(data)
    
    def save_to_json(self, log_data: CloudTrailLogData, file_path: str) -> None:
        data = {
            'Records': [
                {
                    'eventVersion': event.event_version,
                    'userIdentity': {
                        'type': event.user_identity.type,
                        'principalId': event.user_identity.principal_id,
                        'arn': event.user_identity.arn,
                        'accountId': event.user_identity.account_id,
                        **({
                            'accessKeyId': event.user_identity.access_key_id
                        } if event.user_identity.access_key_id else {}),
                        **({
                            'userName': event.user_identity.user_name
                        } if event.user_identity.user_name else {}),
                        **({
                            'sessionContext': event.user_identity.session_context
                        } if event.user_identity.session_context else {})
                    },
                    'eventTime': event.event_time,
                    'eventSource': event.event_source,
                    'eventName': event.event_name,
                    'awsRegion': event.aws_region,
                    'sourceIPAddress': event.source_ip_address,
                    'userAgent': event.user_agent,
                    'requestParameters': event.request_parameters,
                    'responseElements': event.response_elements,
                    'requestID': event.request_id,
                    'eventID': event.event_id,
                    'readOnly': event.read_only,
                    'eventType': event.event_type,
                    'managementEvent': event.management_event,
                    'recipientAccountId': event.recipient_account_id,
                    'eventCategory': event.event_category,
                    **({
                        'tlsDetails': {
                            'tlsVersion': event.tls_details.tls_version,
                            'cipherSuite': event.tls_details.cipher_suite,
                            'clientProvidedHostHeader': event.tls_details.client_provided_host_header
                        }
                    } if event.tls_details else {}),
                    **({
                        'sessionCredentialFromConsole': event.session_credential_from_console
                    } if event.session_credential_from_console else {}),
                    **({
                        'sharedEventId': event.shared_event_id
                    } if event.shared_event_id else {}),
                    **({
                        'errorCode': event.error_code
                    } if event.error_code else {}),
                    **({
                        'errorMessage': event.error_message
                    } if event.error_message else {}),
                    **({
                        'insightDetails': event.insight_details
                    } if event.insight_details else {}),
                    **({
                        'resources': event.resources
                    } if event.resources else {})
                } for event in log_data.records
            ]
        }
        
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
