mod reply;
mod request;
mod response;
mod session;
mod client;
use anyhow::Result;
pub use reply::BusReply;
pub use request::BusRequest;
pub use response::BusResponse;
pub use session::BusSession;
pub use client::bus_request;

/// The local socket path to which `lqosd` will bind itself,
/// listening for requets.
pub const BUS_SOCKET_PATH: &str = "/tmp/lqos_bus";

/// Encodes a BusSession with `bincode`, providing a tight binary
/// representation of the request object for TCP transmission.
pub fn encode_request(request: &BusSession) -> Result<Vec<u8>> {
    Ok(bincode::serialize(request)?)
}

/// Decodes bytes into a `BusSession`.
pub fn decode_request(bytes: &[u8]) -> Result<BusSession> {
    Ok(bincode::deserialize(&bytes)?)
}

/// Encodes a `BusReply` object with `bincode`.
pub fn encode_response(request: &BusReply) -> Result<Vec<u8>> {
    Ok(bincode::serialize(request)?)
}

/// Decodes a `BusReply` object with `bincode`.
pub fn decode_response(bytes: &[u8]) -> Result<BusReply> {
    Ok(bincode::deserialize(&bytes)?)
}

/// The cookie value to use to determine that the session is valid.
pub fn cookie_value() -> u32 {
    1234
}

#[cfg(test)]
mod test {
    use super::*;
    use crate::{BusRequest, BusResponse};

    #[test]
    fn test_session_roundtrip() {
        let session = BusSession {
            auth_cookie: cookie_value(),
            requests: vec![BusRequest::Ping],
        };

        let bytes = encode_request(&session).unwrap();
        let new_session = decode_request(&bytes).unwrap();
        assert_eq!(new_session.auth_cookie, session.auth_cookie);
        assert_eq!(new_session.requests.len(), session.requests.len());
        assert_eq!(new_session.requests[0], session.requests[0]);
    }

    #[test]
    fn test_reply_roundtrip() {
        let reply = BusReply {
            auth_cookie: cookie_value(),
            responses: vec![BusResponse::Ack],
        };
        let bytes = encode_response(&reply).unwrap();
        let new_reply = decode_response(&bytes).unwrap();
        assert_eq!(reply.auth_cookie, new_reply.auth_cookie);
        assert_eq!(reply.responses.len(), new_reply.responses.len());
        assert_eq!(reply.responses[0], new_reply.responses[0]);
    }
}
