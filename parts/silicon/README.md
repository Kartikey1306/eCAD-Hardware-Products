# Silicon parts catalog

Flight- and frontier-grade silicon relevant to the EmbeddedOS (EoS)
ecosystem: AI accelerators, space-grade parts, and new wireless SoCs worth
tracking for board support and the agent-fabric hardware story.

This catalog is **not** the board catalog (`boards/`, tracked by #28).
Board records carry a strict evidence contract (SHA-256 of retrieved CAD
files); part records here carry sourced facts only — no procurement
implied, no CAD availability claimed.

Record fields: `part_id`, `manufacturer`, `part`, `family`, `category`,
`status` (announced / sampling / production), `package`, `key_specs`,
`compatibility`, `qualification`, `datasheet`, `sources`, `added`, `notes`.
Facts must cite a source; thin facts are marked as such.
