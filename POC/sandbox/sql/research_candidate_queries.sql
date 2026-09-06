-- High-ST event candidates from the current gold event summary.
SELECT
    event_id,
    run,
    luminosityBlock,
    event,
    n_muons,
    n_jets,
    leading_muon_pt,
    leading_jet_pt,
    MET_pt,
    HT,
    ST
FROM event_summary
ORDER BY ST DESC
LIMIT 50;

-- Z-like dimuon candidates.
SELECT
    event_id,
    run,
    luminosityBlock,
    event,
    muon1_pt,
    muon2_pt,
    invariant_mass,
    delta_r
FROM dimuon
WHERE invariant_mass BETWEEN 70 AND 110
ORDER BY abs(invariant_mass - 91.1876)
LIMIT 50;

-- Sparse event-region summary using simple binned kinematics.
SELECT
    n_muons,
    n_jets,
    floor(MET_pt / 25) * 25 AS met_bin_low,
    floor(ST / 100) * 100 AS st_bin_low,
    count(*) AS events
FROM event_summary
GROUP BY n_muons, n_jets, met_bin_low, st_bin_low
ORDER BY events ASC, st_bin_low DESC
LIMIT 100;

