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
LIMIT 25;

