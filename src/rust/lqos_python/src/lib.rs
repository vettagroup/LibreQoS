use lqos_bus::{BusRequest, BusResponse, TcHandle};
use pyo3::{
    exceptions::PyOSError, pyclass, pyfunction, pymodule, types::PyModule, wrap_pyfunction,
    PyResult, Python,
};
mod blocking;
use anyhow::{Error, Result};
use blocking::run_query;

/// Defines the Python module exports.
/// All exported functions have to be listed here.
#[pymodule]
fn liblqos_python(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<PyIpMapping>()?;
    m.add_wrapped(wrap_pyfunction!(is_lqosd_alive))?;
    m.add_wrapped(wrap_pyfunction!(list_ip_mappings))?;
    m.add_wrapped(wrap_pyfunction!(clear_ip_mappings))?;
    m.add_wrapped(wrap_pyfunction!(delete_ip_mapping))?;
    m.add_wrapped(wrap_pyfunction!(add_ip_mapping))?;
    Ok(())
}

/// Check that `lqosd` is running.
///
/// Returns true if it is running, false otherwise.
#[pyfunction]
fn is_lqosd_alive(_py: Python) -> PyResult<bool> {
    if let Ok(reply) = run_query(vec![BusRequest::Ping]) {
        for resp in reply.iter() {
            match resp {
                BusResponse::Ack => return Ok(true),
                _ => {}
            }
        }
    }
    Ok(false)
}

/// Provides a representation of an IP address mapping
/// Available through python by field name.
#[pyclass]
pub struct PyIpMapping {
    #[pyo3(get)]
    pub ip_address: String,
    #[pyo3(get)]
    pub prefix_length: u32,
    #[pyo3(get)]
    pub tc_handle: (u16, u16),
    #[pyo3(get)]
    pub cpu: u32,
}

/// Returns a list of all IP mappings
#[pyfunction]
fn list_ip_mappings(_py: Python) -> PyResult<Vec<PyIpMapping>> {
    let mut result = Vec::new();
    if let Ok(reply) = run_query(vec![BusRequest::ListIpFlow]) {
        for resp in reply.iter() {
            match resp {
                BusResponse::MappedIps(map) => {
                    for mapping in map.iter() {
                        result.push(PyIpMapping {
                            ip_address: mapping.ip_address.clone(),
                            prefix_length: mapping.prefix_length,
                            tc_handle: mapping.tc_handle.get_major_minor(),
                            cpu: mapping.cpu,
                        });
                    }
                }
                _ => {}
            }
        }
    }
    Ok(result)
}

/// Clear all IP address to TC/CPU mappings
#[pyfunction]
fn clear_ip_mappings(_py: Python) -> PyResult<()> {
    run_query(vec![BusRequest::ClearIpFlow]).unwrap();
    Ok(())
}

/// Deletes an IP to CPU/TC mapping.
///
/// ## Arguments
///
/// * `ip_address`: The IP address to unmap.
/// * `upload`: `true` if this needs to be applied to the upload map (for a split/stick setup)
#[pyfunction]
fn delete_ip_mapping(_py: Python, ip_address: String, upload: bool) -> PyResult<()> {
    run_query(vec![BusRequest::DelIpFlow { ip_address, upload }]).unwrap();
    Ok(())
}

/// Internal function
/// Converts IP address arguments into an IP mapping request.
fn parse_add_ip(ip: &str, classid: &str, cpu: &str, upload: bool) -> Result<BusRequest> {
    if !classid.contains(":") {
        return Err(Error::msg(
            "Class id must be in the format (major):(minor), e.g. 1:12",
        ));
    }
    Ok(BusRequest::MapIpToFlow {
        ip_address: ip.to_string(),
        tc_handle: TcHandle::from_string(classid)?,
        cpu: u32::from_str_radix(&cpu.replace("0x", ""), 16)?, // Force HEX representation
        upload,
    })
}

/// Adds an IP address mapping
#[pyfunction]
fn add_ip_mapping(ip: String, classid: String, cpu: String, upload: bool) -> PyResult<()> {
    let request = parse_add_ip(&ip, &classid, &cpu, upload);
    if let Ok(request) = request {
        run_query(vec![request]).unwrap();
        Ok(())
    } else {
        Err(PyOSError::new_err(request.err().unwrap().to_string()))
    }
}
