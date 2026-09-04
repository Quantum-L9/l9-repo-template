# Source Lineage and Supersession Protocol

For uploaded packs or multi-source inputs:

1. inventory every source
2. hash exact bytes where available
3. detect exact duplicates mechanically
4. identify semantic duplicates/candidates separately
5. extract dates/versions/authority signals
6. build supersession and derivation candidates
7. record contradictions
8. assign every source exactly one disposition:
   - `use`
   - `reference_only`
   - `quarantine`
   - `ignore`
9. synthesize only from approved sources

No source may disappear silently from the accounting.
