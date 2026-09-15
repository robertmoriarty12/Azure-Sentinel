# ASIM Mapping Proposals

This directory stores reviewable proposals for mappings from Microsoft-supported solution content to ASIM schemas.

Use `instructions/classify-existing-asim-content.md` to create a proposal. A proposal does not affect runtime classification. Only entries in `database/asim-mapping-registry.yaml` with `reviewState: approved` are applied during a database refresh.

Keep each proposal narrow: one product or source family, one or more closely related ASIM schemas, documented evidence, positive examples, and explicit false-positive boundaries.