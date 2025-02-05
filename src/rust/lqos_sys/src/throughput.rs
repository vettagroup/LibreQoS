use lqos_utils::XdpIpAddress;

use crate::{bpf_per_cpu_map::BpfPerCpuMap};

/// Representation of the XDP map from map_traffic
#[repr(C)]
#[derive(Debug, Clone, Default)]
pub struct HostCounter {
  /// Download bytes counter (keeps incrementing)
  pub download_bytes: u64,

  /// Upload bytes counter (keeps incrementing)
  pub upload_bytes: u64,

  /// Download packets counter (keeps incrementing)
  pub download_packets: u64,

  /// Upload packets counter (keeps incrementing)
  pub upload_packets: u64,

  /// Mapped TC handle, 0 if there isn't one.
  pub tc_handle: u32,

  /// Time last seen, in nanoseconds since kernel boot
  pub last_seen: u64,
}

/// Iterates through all throughput entries, and sends them in turn to `callback`.
/// This elides the need to clone or copy data.
pub fn throughput_for_each(
  callback: &mut dyn FnMut(&XdpIpAddress, &[HostCounter]),
) {
  if let Ok(throughput) = BpfPerCpuMap::<XdpIpAddress, HostCounter>::from_path(
    "/sys/fs/bpf/map_traffic",
  ) {
    throughput.for_each(callback);
  }
}
