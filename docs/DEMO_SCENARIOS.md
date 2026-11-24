# Fictional Meridian Equipment Group demo data

All entities and outcomes are fictional and deterministic. Scenario reference dates are fixed; generated audit timestamps use UTC runtime time. Inventory's `availableQuantity` is physical on-hand stock; `committedQuantity` is already reserved and must be subtracted once to derive allocatable stock.

- **SCN-001 Single Parts Transfer:** five physical units at North, two already committed to repairs. Moving all five leaves a two-unit shortfall; The existing repairs remain reserved; the original five-unit transfer is infeasible. Sourcing the missing two units from West preserves the original transfer requirement, subject to delivery constraints.
- **SCN-002 Combined Pending Decisions:** PART-HP220 has North physical inventory 10 and West inventory 5, of which 2 are committed (3 unallocated). Decisions D-101 (transfer 4), D-102 (customer repairs 4), D-103 (rental preparation 3) are each feasible alone; together they demand 11 against 10, leaving a one-unit shortage. The evaluator derives deficits, customer risk and alternative feasibility from inputs.
- **SCN-003 Equipment Allocation Conflict:** EQ-101 sale, maintenance and rental time intervals overlap Thursday–Friday. EQ-102 is a compatible ready replacement, subject to positioning time. Timeline dates and readiness are deterministic.

Revenue-at-risk is an estimate from affected commitment records, not confirmed financial loss. Existing reservations are not included twice. Unsupported impacts must be unknown rather than fabricated. Demo reset restores fixture state and retains audit history.
