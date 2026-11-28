# Preserve the serving Integration tick and batch vendor table

The production Integration manifest now declares a 20-second serving tick and
the incumbent `en-overflow-1116` batch route table. The projection pump overrides
both inherited settings with its prior values. Staging keeps its 10-second
tick and mirrors Integration's vendor table.

Release admission still requires a preview against the serving Integration
revision. The preview must show literal follow-up slots of 4 and account for
any V3 or parked-terminal additions before traffic moves.
