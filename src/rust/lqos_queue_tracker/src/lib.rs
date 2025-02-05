mod bus;
mod circuit_to_queue;
mod interval;
mod queue_diff;
mod queue_store;
mod queue_structure;
mod queue_types;
mod tracking;

/// How many history items do we store?
const NUM_QUEUE_HISTORY: usize = 600;

pub use bus::get_raw_circuit_data;
pub use interval::set_queue_refresh_interval;
pub use queue_structure::spawn_queue_structure_monitor;
pub use queue_types::deserialize_tc_tree; // Exported for the benchmarker
pub use tracking::spawn_queue_monitor;
pub use tracking::{add_watched_queue, still_watching};
