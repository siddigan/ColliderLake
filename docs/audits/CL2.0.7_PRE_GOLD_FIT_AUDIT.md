# CL2.0.7-pre Gold/Fit Audit ? Part 1 (read-only)



Part 1 audit: existing Parquet and fit outputs were read without mutation. DuckDB used an in-memory connection and a temporary spill directory under the OS temporary directory, outside data/. Both duplicate checks are zero, so the Part 2 gate is satisfied.



## Sources and reproducibility



- Gold Parquet: C:\Ewok\Abomination\Theory of E\V-TRY\ColliderLake\data\gold\analysis=resonance\dataset=run2012bc_doublemuparked\dimuon/*.parquet (179 files).

- Silver selected muons: C:\Ewok\Abomination\Theory of E\V-TRY\ColliderLake\data\silver\dataset=run2012bc_doublemuparked\muons/*.parquet (179 files).

- Fit results: data/results/analysis=resonance/dataset=run2012bc_doublemuparked/fits.json and fits.parquet.

- Fit config: configs/fits/resonance_ladder.yaml; code: src/physics/fitting.py, src/physics/models.py; constants: src/physics/pdg.py.

- The SQL below uses explicit absolute-path globs; each resolved to the listed 179 files.



DuckDB audit settings: memory_limit=2GB, temp_directory=<OS temporary directory>, preserve_insertion_order=false, threads=4.



## A. Gold population audit



| Metric | Exact value |

|---|---:|

| Gold pair rows | 83,057,658 |

| Distinct full event keys | 42,812,309 |

| Duplicate full-key extra rows (dataset_id, run, luminosityBlock, event, pair_idx) | 0 |

| Duplicate canonical-pair extra rows (full event key, mu1_idx, mu2_idx) | 0 |

| Pairs/event max | 612 |

| Pairs/event p99, quantile_cont | 10.0 |

| Pairs/event p99.9, quantile_cont | 24.0 |



Both duplicate audits are zero. Canonical pairs were grouped by the full event key plus muon indices, never by muon indices alone.



### Exact SQL



Population:



    SELECT count(*) AS pair_rows, count(DISTINCT (dataset_id, run, luminosityBlock, event)) AS distinct_events

    FROM read_parquet('C:/Ewok/Abomination/Theory of E/V-TRY/ColliderLake/data/gold/analysis=resonance/dataset=run2012bc_doublemuparked/dimuon/*.parquet');



Duplicate full key:



    SELECT coalesce(sum(c - 1), 0) AS duplicate_full_key_rows

    FROM (SELECT count(*) AS c

          FROM read_parquet('C:/Ewok/Abomination/Theory of E/V-TRY/ColliderLake/data/gold/analysis=resonance/dataset=run2012bc_doublemuparked/dimuon/*.parquet')

          GROUP BY dataset_id, run, luminosityBlock, event, pair_idx

          HAVING count(*) > 1);



Duplicate canonical pair:



    SELECT coalesce(sum(c - 1), 0) AS duplicate_canonical_pair_rows

    FROM (SELECT count(*) AS c

          FROM read_parquet('C:/Ewok/Abomination/Theory of E/V-TRY/ColliderLake/data/gold/analysis=resonance/dataset=run2012bc_doublemuparked/dimuon/*.parquet')

          GROUP BY dataset_id, run, luminosityBlock, event, mu1_idx, mu2_idx

          HAVING count(*) > 1);



Pairs/event quantiles:



    WITH event_pairs AS (

      SELECT dataset_id, run, luminosityBlock, event, count(*) AS pairs

      FROM read_parquet('C:/Ewok/Abomination/Theory of E/V-TRY/ColliderLake/data/gold/analysis=resonance/dataset=run2012bc_doublemuparked/dimuon/*.parquet')

      GROUP BY dataset_id, run, luminosityBlock, event

    )

    SELECT max(pairs), quantile_cont(pairs, 0.99), quantile_cont(pairs, 0.999)

    FROM event_pairs;



### Gold rows per Parquet part



| Part | Rows | Bytes |

|---|---:|---:|

| Run2012BC_DoubleMuParked_Muons_part_0000.parquet | 439,844 | 32,821,741 |

| Run2012BC_DoubleMuParked_Muons_part_0001.parquet | 442,127 | 32,927,946 |

| Run2012BC_DoubleMuParked_Muons_part_0002.parquet | 442,736 | 32,925,105 |

| Run2012BC_DoubleMuParked_Muons_part_0003.parquet | 440,760 | 32,845,486 |

| Run2012BC_DoubleMuParked_Muons_part_0004.parquet | 441,938 | 32,945,067 |

| Run2012BC_DoubleMuParked_Muons_part_0005.parquet | 441,138 | 32,856,348 |

| Run2012BC_DoubleMuParked_Muons_part_0006.parquet | 442,579 | 32,957,723 |

| Run2012BC_DoubleMuParked_Muons_part_0007.parquet | 440,932 | 32,852,899 |

| Run2012BC_DoubleMuParked_Muons_part_0008.parquet | 440,467 | 32,846,711 |

| Run2012BC_DoubleMuParked_Muons_part_0009.parquet | 442,165 | 32,949,784 |

| Run2012BC_DoubleMuParked_Muons_part_0010.parquet | 437,965 | 32,685,565 |

| Run2012BC_DoubleMuParked_Muons_part_0011.parquet | 438,651 | 32,727,016 |

| Run2012BC_DoubleMuParked_Muons_part_0012.parquet | 441,643 | 32,879,200 |

| Run2012BC_DoubleMuParked_Muons_part_0013.parquet | 440,301 | 32,838,752 |

| Run2012BC_DoubleMuParked_Muons_part_0014.parquet | 440,249 | 32,862,762 |

| Run2012BC_DoubleMuParked_Muons_part_0015.parquet | 440,739 | 32,832,209 |

| Run2012BC_DoubleMuParked_Muons_part_0016.parquet | 442,272 | 32,936,705 |

| Run2012BC_DoubleMuParked_Muons_part_0017.parquet | 443,156 | 33,023,996 |

| Run2012BC_DoubleMuParked_Muons_part_0018.parquet | 442,486 | 32,948,110 |

| Run2012BC_DoubleMuParked_Muons_part_0019.parquet | 442,433 | 32,975,164 |

| Run2012BC_DoubleMuParked_Muons_part_0020.parquet | 445,126 | 33,098,953 |

| Run2012BC_DoubleMuParked_Muons_part_0021.parquet | 439,853 | 32,765,175 |

| Run2012BC_DoubleMuParked_Muons_part_0022.parquet | 440,482 | 32,838,103 |

| Run2012BC_DoubleMuParked_Muons_part_0023.parquet | 441,483 | 32,899,556 |

| Run2012BC_DoubleMuParked_Muons_part_0024.parquet | 440,666 | 32,833,030 |

| Run2012BC_DoubleMuParked_Muons_part_0025.parquet | 440,615 | 32,832,093 |

| Run2012BC_DoubleMuParked_Muons_part_0026.parquet | 442,311 | 32,934,200 |

| Run2012BC_DoubleMuParked_Muons_part_0027.parquet | 441,809 | 32,880,588 |

| Run2012BC_DoubleMuParked_Muons_part_0028.parquet | 439,038 | 32,768,715 |

| Run2012BC_DoubleMuParked_Muons_part_0029.parquet | 439,224 | 32,765,805 |

| Run2012BC_DoubleMuParked_Muons_part_0030.parquet | 438,756 | 32,739,802 |

| Run2012BC_DoubleMuParked_Muons_part_0031.parquet | 439,923 | 32,774,250 |

| Run2012BC_DoubleMuParked_Muons_part_0032.parquet | 439,408 | 32,741,382 |

| Run2012BC_DoubleMuParked_Muons_part_0033.parquet | 439,787 | 32,814,590 |

| Run2012BC_DoubleMuParked_Muons_part_0034.parquet | 438,354 | 32,694,243 |

| Run2012BC_DoubleMuParked_Muons_part_0035.parquet | 440,473 | 32,833,611 |

| Run2012BC_DoubleMuParked_Muons_part_0036.parquet | 440,993 | 32,862,175 |

| Run2012BC_DoubleMuParked_Muons_part_0037.parquet | 441,543 | 32,904,104 |

| Run2012BC_DoubleMuParked_Muons_part_0038.parquet | 439,599 | 32,813,483 |

| Run2012BC_DoubleMuParked_Muons_part_0039.parquet | 438,991 | 32,796,095 |

| Run2012BC_DoubleMuParked_Muons_part_0040.parquet | 436,840 | 32,607,342 |

| Run2012BC_DoubleMuParked_Muons_part_0041.parquet | 437,991 | 32,636,977 |

| Run2012BC_DoubleMuParked_Muons_part_0042.parquet | 442,135 | 32,925,924 |

| Run2012BC_DoubleMuParked_Muons_part_0043.parquet | 438,008 | 32,716,864 |

| Run2012BC_DoubleMuParked_Muons_part_0044.parquet | 439,371 | 32,766,640 |

| Run2012BC_DoubleMuParked_Muons_part_0045.parquet | 440,463 | 32,839,852 |

| Run2012BC_DoubleMuParked_Muons_part_0046.parquet | 442,377 | 32,941,718 |

| Run2012BC_DoubleMuParked_Muons_part_0047.parquet | 437,692 | 32,708,405 |

| Run2012BC_DoubleMuParked_Muons_part_0048.parquet | 439,470 | 32,784,936 |

| Run2012BC_DoubleMuParked_Muons_part_0049.parquet | 440,658 | 32,837,590 |

| Run2012BC_DoubleMuParked_Muons_part_0050.parquet | 440,090 | 32,847,968 |

| Run2012BC_DoubleMuParked_Muons_part_0051.parquet | 442,253 | 32,941,335 |

| Run2012BC_DoubleMuParked_Muons_part_0052.parquet | 440,912 | 32,874,679 |

| Run2012BC_DoubleMuParked_Muons_part_0053.parquet | 441,446 | 32,902,870 |

| Run2012BC_DoubleMuParked_Muons_part_0054.parquet | 439,219 | 32,756,198 |

| Run2012BC_DoubleMuParked_Muons_part_0055.parquet | 439,136 | 32,716,359 |

| Run2012BC_DoubleMuParked_Muons_part_0056.parquet | 440,624 | 32,871,361 |

| Run2012BC_DoubleMuParked_Muons_part_0057.parquet | 438,192 | 32,661,692 |

| Run2012BC_DoubleMuParked_Muons_part_0058.parquet | 441,926 | 32,930,701 |

| Run2012BC_DoubleMuParked_Muons_part_0059.parquet | 439,610 | 32,789,344 |

| Run2012BC_DoubleMuParked_Muons_part_0060.parquet | 438,491 | 32,692,294 |

| Run2012BC_DoubleMuParked_Muons_part_0061.parquet | 438,386 | 32,697,601 |

| Run2012BC_DoubleMuParked_Muons_part_0062.parquet | 440,285 | 32,831,752 |

| Run2012BC_DoubleMuParked_Muons_part_0063.parquet | 441,105 | 32,879,425 |

| Run2012BC_DoubleMuParked_Muons_part_0064.parquet | 442,489 | 32,932,952 |

| Run2012BC_DoubleMuParked_Muons_part_0065.parquet | 441,575 | 32,881,669 |

| Run2012BC_DoubleMuParked_Muons_part_0066.parquet | 442,909 | 32,969,841 |

| Run2012BC_DoubleMuParked_Muons_part_0067.parquet | 443,271 | 32,968,712 |

| Run2012BC_DoubleMuParked_Muons_part_0068.parquet | 442,071 | 32,916,511 |

| Run2012BC_DoubleMuParked_Muons_part_0069.parquet | 442,310 | 32,942,157 |

| Run2012BC_DoubleMuParked_Muons_part_0070.parquet | 437,538 | 32,680,180 |

| Run2012BC_DoubleMuParked_Muons_part_0071.parquet | 441,424 | 32,908,388 |

| Run2012BC_DoubleMuParked_Muons_part_0072.parquet | 441,873 | 32,821,892 |

| Run2012BC_DoubleMuParked_Muons_part_0073.parquet | 444,569 | 33,044,905 |

| Run2012BC_DoubleMuParked_Muons_part_0074.parquet | 440,634 | 32,870,073 |

| Run2012BC_DoubleMuParked_Muons_part_0075.parquet | 455,926 | 33,839,104 |

| Run2012BC_DoubleMuParked_Muons_part_0076.parquet | 488,774 | 36,042,792 |

| Run2012BC_DoubleMuParked_Muons_part_0077.parquet | 482,327 | 35,595,157 |

| Run2012BC_DoubleMuParked_Muons_part_0078.parquet | 477,549 | 35,314,400 |

| Run2012BC_DoubleMuParked_Muons_part_0079.parquet | 477,881 | 35,311,788 |

| Run2012BC_DoubleMuParked_Muons_part_0080.parquet | 491,955 | 36,198,064 |

| Run2012BC_DoubleMuParked_Muons_part_0081.parquet | 480,013 | 35,500,995 |

| Run2012BC_DoubleMuParked_Muons_part_0082.parquet | 486,009 | 35,842,293 |

| Run2012BC_DoubleMuParked_Muons_part_0083.parquet | 478,759 | 35,390,135 |

| Run2012BC_DoubleMuParked_Muons_part_0084.parquet | 481,408 | 35,549,565 |

| Run2012BC_DoubleMuParked_Muons_part_0085.parquet | 481,749 | 35,630,143 |

| Run2012BC_DoubleMuParked_Muons_part_0086.parquet | 483,786 | 35,721,214 |

| Run2012BC_DoubleMuParked_Muons_part_0087.parquet | 489,121 | 36,013,011 |

| Run2012BC_DoubleMuParked_Muons_part_0088.parquet | 478,159 | 35,323,598 |

| Run2012BC_DoubleMuParked_Muons_part_0089.parquet | 479,797 | 35,472,985 |

| Run2012BC_DoubleMuParked_Muons_part_0090.parquet | 490,015 | 36,132,578 |

| Run2012BC_DoubleMuParked_Muons_part_0091.parquet | 483,660 | 35,673,796 |

| Run2012BC_DoubleMuParked_Muons_part_0092.parquet | 478,148 | 35,346,934 |

| Run2012BC_DoubleMuParked_Muons_part_0093.parquet | 488,385 | 35,996,486 |

| Run2012BC_DoubleMuParked_Muons_part_0094.parquet | 486,687 | 35,841,215 |

| Run2012BC_DoubleMuParked_Muons_part_0095.parquet | 476,177 | 35,222,376 |

| Run2012BC_DoubleMuParked_Muons_part_0096.parquet | 487,368 | 35,921,268 |

| Run2012BC_DoubleMuParked_Muons_part_0097.parquet | 485,679 | 35,858,747 |

| Run2012BC_DoubleMuParked_Muons_part_0098.parquet | 485,704 | 35,809,543 |

| Run2012BC_DoubleMuParked_Muons_part_0099.parquet | 484,271 | 35,737,487 |

| Run2012BC_DoubleMuParked_Muons_part_0100.parquet | 482,223 | 35,558,182 |

| Run2012BC_DoubleMuParked_Muons_part_0101.parquet | 483,982 | 35,722,209 |

| Run2012BC_DoubleMuParked_Muons_part_0102.parquet | 481,986 | 35,611,455 |

| Run2012BC_DoubleMuParked_Muons_part_0103.parquet | 480,836 | 35,530,063 |

| Run2012BC_DoubleMuParked_Muons_part_0104.parquet | 483,342 | 35,674,744 |

| Run2012BC_DoubleMuParked_Muons_part_0105.parquet | 483,919 | 35,723,336 |

| Run2012BC_DoubleMuParked_Muons_part_0106.parquet | 475,785 | 35,217,236 |

| Run2012BC_DoubleMuParked_Muons_part_0107.parquet | 482,086 | 35,596,627 |

| Run2012BC_DoubleMuParked_Muons_part_0108.parquet | 477,725 | 35,376,579 |

| Run2012BC_DoubleMuParked_Muons_part_0109.parquet | 480,913 | 35,498,221 |

| Run2012BC_DoubleMuParked_Muons_part_0110.parquet | 481,088 | 35,557,397 |

| Run2012BC_DoubleMuParked_Muons_part_0111.parquet | 486,824 | 35,895,611 |

| Run2012BC_DoubleMuParked_Muons_part_0112.parquet | 477,235 | 35,333,336 |

| Run2012BC_DoubleMuParked_Muons_part_0113.parquet | 486,732 | 35,945,072 |

| Run2012BC_DoubleMuParked_Muons_part_0114.parquet | 488,768 | 36,049,871 |

| Run2012BC_DoubleMuParked_Muons_part_0115.parquet | 481,170 | 35,609,708 |

| Run2012BC_DoubleMuParked_Muons_part_0116.parquet | 483,403 | 35,705,456 |

| Run2012BC_DoubleMuParked_Muons_part_0117.parquet | 483,945 | 35,762,691 |

| Run2012BC_DoubleMuParked_Muons_part_0118.parquet | 471,017 | 34,905,854 |

| Run2012BC_DoubleMuParked_Muons_part_0119.parquet | 486,109 | 35,854,818 |

| Run2012BC_DoubleMuParked_Muons_part_0120.parquet | 479,084 | 35,439,406 |

| Run2012BC_DoubleMuParked_Muons_part_0121.parquet | 472,475 | 34,999,021 |

| Run2012BC_DoubleMuParked_Muons_part_0122.parquet | 484,202 | 35,743,106 |

| Run2012BC_DoubleMuParked_Muons_part_0123.parquet | 476,106 | 35,246,537 |

| Run2012BC_DoubleMuParked_Muons_part_0124.parquet | 481,117 | 35,547,391 |

| Run2012BC_DoubleMuParked_Muons_part_0125.parquet | 481,781 | 35,625,916 |

| Run2012BC_DoubleMuParked_Muons_part_0126.parquet | 480,178 | 35,498,404 |

| Run2012BC_DoubleMuParked_Muons_part_0127.parquet | 478,480 | 35,440,870 |

| Run2012BC_DoubleMuParked_Muons_part_0128.parquet | 477,274 | 35,305,729 |

| Run2012BC_DoubleMuParked_Muons_part_0129.parquet | 481,113 | 35,573,766 |

| Run2012BC_DoubleMuParked_Muons_part_0130.parquet | 484,026 | 35,774,483 |

| Run2012BC_DoubleMuParked_Muons_part_0131.parquet | 476,600 | 35,276,184 |

| Run2012BC_DoubleMuParked_Muons_part_0132.parquet | 480,484 | 35,550,314 |

| Run2012BC_DoubleMuParked_Muons_part_0133.parquet | 484,198 | 35,762,076 |

| Run2012BC_DoubleMuParked_Muons_part_0134.parquet | 479,758 | 35,493,773 |

| Run2012BC_DoubleMuParked_Muons_part_0135.parquet | 484,146 | 35,745,623 |

| Run2012BC_DoubleMuParked_Muons_part_0136.parquet | 481,054 | 35,536,295 |

| Run2012BC_DoubleMuParked_Muons_part_0137.parquet | 473,004 | 35,041,550 |

| Run2012BC_DoubleMuParked_Muons_part_0138.parquet | 480,763 | 35,485,384 |

| Run2012BC_DoubleMuParked_Muons_part_0139.parquet | 482,083 | 35,599,923 |

| Run2012BC_DoubleMuParked_Muons_part_0140.parquet | 478,556 | 35,417,568 |

| Run2012BC_DoubleMuParked_Muons_part_0141.parquet | 474,866 | 35,151,720 |

| Run2012BC_DoubleMuParked_Muons_part_0142.parquet | 484,923 | 35,823,765 |

| Run2012BC_DoubleMuParked_Muons_part_0143.parquet | 479,063 | 35,448,703 |

| Run2012BC_DoubleMuParked_Muons_part_0144.parquet | 478,156 | 35,362,737 |

| Run2012BC_DoubleMuParked_Muons_part_0145.parquet | 479,455 | 35,475,206 |

| Run2012BC_DoubleMuParked_Muons_part_0146.parquet | 482,557 | 35,636,443 |

| Run2012BC_DoubleMuParked_Muons_part_0147.parquet | 486,873 | 35,966,745 |

| Run2012BC_DoubleMuParked_Muons_part_0148.parquet | 477,947 | 35,324,162 |

| Run2012BC_DoubleMuParked_Muons_part_0149.parquet | 494,116 | 36,308,334 |

| Run2012BC_DoubleMuParked_Muons_part_0150.parquet | 491,282 | 36,167,330 |

| Run2012BC_DoubleMuParked_Muons_part_0151.parquet | 484,126 | 35,694,688 |

| Run2012BC_DoubleMuParked_Muons_part_0152.parquet | 492,036 | 36,167,927 |

| Run2012BC_DoubleMuParked_Muons_part_0153.parquet | 494,059 | 36,282,579 |

| Run2012BC_DoubleMuParked_Muons_part_0154.parquet | 489,119 | 36,024,449 |

| Run2012BC_DoubleMuParked_Muons_part_0155.parquet | 491,672 | 36,125,315 |

| Run2012BC_DoubleMuParked_Muons_part_0156.parquet | 490,310 | 36,045,481 |

| Run2012BC_DoubleMuParked_Muons_part_0157.parquet | 485,360 | 35,773,310 |

| Run2012BC_DoubleMuParked_Muons_part_0158.parquet | 493,176 | 36,272,651 |

| Run2012BC_DoubleMuParked_Muons_part_0159.parquet | 493,316 | 36,250,464 |

| Run2012BC_DoubleMuParked_Muons_part_0160.parquet | 495,958 | 36,428,612 |

| Run2012BC_DoubleMuParked_Muons_part_0161.parquet | 495,631 | 36,348,194 |

| Run2012BC_DoubleMuParked_Muons_part_0162.parquet | 493,034 | 36,260,574 |

| Run2012BC_DoubleMuParked_Muons_part_0163.parquet | 483,864 | 35,675,510 |

| Run2012BC_DoubleMuParked_Muons_part_0164.parquet | 491,415 | 36,193,780 |

| Run2012BC_DoubleMuParked_Muons_part_0165.parquet | 490,349 | 36,104,529 |

| Run2012BC_DoubleMuParked_Muons_part_0166.parquet | 480,294 | 35,517,798 |

| Run2012BC_DoubleMuParked_Muons_part_0167.parquet | 479,220 | 35,452,813 |

| Run2012BC_DoubleMuParked_Muons_part_0168.parquet | 484,213 | 35,766,073 |

| Run2012BC_DoubleMuParked_Muons_part_0169.parquet | 487,115 | 35,958,323 |

| Run2012BC_DoubleMuParked_Muons_part_0170.parquet | 480,136 | 35,543,464 |

| Run2012BC_DoubleMuParked_Muons_part_0171.parquet | 478,037 | 35,368,145 |

| Run2012BC_DoubleMuParked_Muons_part_0172.parquet | 481,057 | 35,576,713 |

| Run2012BC_DoubleMuParked_Muons_part_0173.parquet | 477,252 | 35,330,064 |

| Run2012BC_DoubleMuParked_Muons_part_0174.parquet | 483,021 | 35,711,171 |

| Run2012BC_DoubleMuParked_Muons_part_0175.parquet | 483,856 | 35,751,985 |

| Run2012BC_DoubleMuParked_Muons_part_0176.parquet | 477,015 | 35,333,583 |

| Run2012BC_DoubleMuParked_Muons_part_0177.parquet | 482,639 | 35,663,940 |

| Run2012BC_DoubleMuParked_Muons_part_0178.parquet | 265,905 | 21,031,383 |



179 parts; row-count range 265,905?495,958; total 83,057,658.



### Silver-muon multiplicity attribution



Selected-muon multiplicity is counted from silver per complete event key, joined to gold pair rows aggregated per the same complete event key.



| Threshold | Qualifying joined events | Gold pair rows contributed |

|---|---:|---:|

| >16 selected muons | 2,909 | 319,977 |

| >32 selected muons | 131 | 42,058 |

| >40 selected muons | 17 | 7,802 |



SQL executed for attribution (the USING list is the full event key):



    WITH silver_multiplicity AS (

      SELECT dataset_id, run, luminosityBlock, event, count(*) AS selected_muons

      FROM read_parquet('C:/Ewok/Abomination/Theory of E/V-TRY/ColliderLake/data/silver/dataset=run2012bc_doublemuparked/muons/*.parquet')

      GROUP BY dataset_id, run, luminosityBlock, event

    ), gold_pair_rows AS (

      SELECT dataset_id, run, luminosityBlock, event, count(*) AS gold_pair_rows

      FROM read_parquet('C:/Ewok/Abomination/Theory of E/V-TRY/ColliderLake/data/gold/analysis=resonance/dataset=run2012bc_doublemuparked/dimuon/*.parquet')

      GROUP BY dataset_id, run, luminosityBlock, event

    ), joined AS (

      SELECT s.selected_muons, g.gold_pair_rows

      FROM silver_multiplicity AS s

      INNER JOIN gold_pair_rows AS g USING (dataset_id, run, luminosityBlock, event)

    )

    SELECT

      count(*) FILTER (WHERE selected_muons > 16) AS events_gt16,

      coalesce(sum(gold_pair_rows) FILTER (WHERE selected_muons > 16), 0) AS pairs_gt16,

      count(*) FILTER (WHERE selected_muons > 32) AS events_gt32,

      coalesce(sum(gold_pair_rows) FILTER (WHERE selected_muons > 32), 0) AS pairs_gt32,

      count(*) FILTER (WHERE selected_muons > 40) AS events_gt40,

      coalesce(sum(gold_pair_rows) FILTER (WHERE selected_muons > 40), 0) AS pairs_gt40

    FROM joined;



### Context ratios



| Quantity | Full | Smoke | Ratio |

|---|---:|---:|---:|

| Gold pair rows | 83,057,658 | 1,324,707 | 62.70x |

| Gold pair-bearing events | 42,812,309 | 1,034,022 | 41.40x |

| Dataset events in supplied run context | 61,540,413 | 1,034,022 | 59.51x (~59.5x) |



The >16 tail contributes 319,977 pair rows (0.385%); >32 contributes 42,058 (0.0506%); >40 contributes 7,802 (0.0094%). The multiplicity tail does not account for the full yield growth.



## B. Mass-histogram audit



Each gold pair row contributes unit weight: this fit path consumes no event weights, and calls np.histogram(selected, bins=100, range=window) without a weights argument. Code selects finite mass inclusively (mass >= low and mass <= high). Since the fit first filters to the window, histogram-input underflow and overflow are both zero; excluded full-population rows below/above are listed separately. Equal-width bins 0?98 are [left,right); bin 99 includes the upper edge, matching NumPy.



| Resonance | Window GeV | Entries | Underflow | Overflow | Empty bins | Max bin count | Max-bin center GeV | Below window | Above window |

|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|

| jpsi | [2.8, 3.4] | 5,927,939 | 0 | 0 | 0 | 289,032 | 3.09100 | 20,671,505 | 56,458,214 |

| psi2s | [3.4, 3.95] | 1,422,576 | 0 | 0 | 0 | 22,351 | 3.67775 | 26,599,444 | 55,035,638 |

| upsilon | [8.5, 11.5] | 4,418,264 | 0 | 0 | 0 | 76,978 | 9.44500 | 35,486,387 | 43,153,007 |

| z | [86.0, 96.0] | 5,187,783 | 0 | 0 | 0 | 94,430 | 90.95000 | 76,535,569 | 1,334,306 |



Each following 100-value list gives exact bin counts at indices 0?99. The 101 edges are exact equal subdivisions: edge i = low + i ? (high-low)/100, with the last edge included in the final bin. This is the unchanged np.histogram code path from CL2.0.6b; that commit changed only the Z window [70,110] ? [86,96].



jpsi, window [2.8, 3.4], 100 bins:



    28302,28242,27927,27572,27812,27595,27823,27818,27583,27741,27568,27560,28056,27844,27969,27929,27883,28014,28294,28022,28316,28677,29042,29829,30030,30452,31315,31893,32956,34663,35762,38251,40597,43670,48108,52624,58530,66392,75993,87860,102339,119700,141920,167001,196075,225376,253735,275446,289032,288147,275379,250893,220360,187665,157182,129224,106920,88183,73671,62563,53402,46516,40955,36255,33083,30561,28358,26671,25147,23990,23109,22329,21739,21217,20852,20516,19923,19952,19401,19252,19200,18895,18343,18248,18285,18083,17911,17802,17964,17409,17222,17268,17345,17112,16957,16889,16837,16653,16586,16377



psi2s, window [3.4, 3.95], 100 bins:



    15168,14945,14798,14885,14782,14597,14677,14312,14625,14494,14377,14283,14365,14228,14202,13879,13896,13915,14071,13920,13604,13811,13797,13706,13669,13673,13662,13645,13695,13877,13836,13714,13819,14069,14232,14217,14306,14537,14936,15296,15715,16194,16759,17560,18056,18633,19406,20639,21559,22053,22351,22134,22349,21318,20585,19946,18841,17698,16880,15951,15304,14957,14230,13672,13382,13005,12728,12567,12207,11822,12070,12019,11528,11855,11802,11734,11395,11475,11321,11393,11163,11360,11142,11178,11062,10948,10945,10984,10967,10868,10873,10949,11036,10853,10733,10851,10923,10657,10722,10749



upsilon, window [8.5, 11.5], 100 bins:



    39116,39077,38898,39111,38668,38948,38916,38868,38429,38423,38763,38556,38687,38838,38866,38610,39240,39280,39020,39701,40038,40317,41139,42076,43970,46514,49379,54457,59671,66858,73382,76978,75026,68409,61600,54557,49768,45945,44068,42647,41646,41263,41049,41789,42793,44468,46382,49160,52136,53986,55426,54073,51489,49725,47375,45933,45845,45997,47225,48932,49908,50131,49817,47189,45792,43403,41690,40996,40052,39793,39228,39038,39092,38478,38473,38707,38749,38774,38758,38707,38357,38546,38485,38869,38962,38841,39094,38757,39144,38944,39005,38936,38925,39050,39166,39160,39169,39311,39489,39773



z, window [86.0, 96.0], 100 bins:



    22513,23090,23576,24242,24951,25621,26512,27078,28263,28652,30179,30985,32185,33025,34433,35957,37147,38599,40012,41258,43107,44715,46520,48254,50068,52294,54315,56450,58693,61146,63713,65553,68031,70694,73267,75660,77601,80208,82159,84440,86347,88486,89231,91153,92575,93534,93645,94351,94393,94430,94230,93788,92738,91749,89718,88210,86490,84083,81973,80384,77229,74482,71997,69271,67721,64376,62060,59294,56813,53933,51576,49704,47039,45203,42998,40811,38884,37099,35755,33868,32499,30875,29406,28282,27120,25658,24851,23672,22627,21518,20818,20042,19199,18225,17453,16724,16160,15911,15357,14599



Reproducible per-window bin-count query (substitute the numeric bounds from the table):



    WITH selected AS (

      SELECT mass

      FROM read_parquet('C:/Ewok/Abomination/Theory of E/V-TRY/ColliderLake/data/gold/analysis=resonance/dataset=run2012bc_doublemuparked/dimuon/*.parquet')

      WHERE isfinite(mass) AND mass >= <low> AND mass <= <high>

    )

    SELECT least(cast(floor((mass - <low>) / ((<high> - <low>) / 100)) AS INTEGER), 99) AS bin,

           count(*) AS entries

    FROM selected GROUP BY 1 ORDER BY 1;



## C. Fit implementation facts (inspection only)



- Objective: extended binned Poisson NLL, computed as 2 ? sum(expected - observed ? log(expected)); the data-only log(n!) term is omitted, so minimization is unchanged.

- Each bin is a Poisson count. Empty bins are retained and contribute their expected-count term. chi2 is Pearson sum((observed-expected)^2/expected) for expected > 0; ndf = bins - free parameters.

- Signal and background shapes are independently normalized by the discrete sum over bin centers in the window. Their free yields multiply those normalized shapes.

- Signal and background yields each initialize to max(total selected entries ? 0.5, 1.0), with bounds [0, unbounded].

- mass_stat_unc is minuit.errors for the mass parameter (offset for triple Gaussian) after minuit.hesse(). The code checks no covariance accuracy or positive-definiteness flag.

- Current status gate in src/physics/fitting.py: if not minuit.fmin.is_valid: raise RuntimeError(...). The returned fit row then sets status to valid unconditionally. assert_valid_fit checks status/convergence and finiteness/positivity of mass, uncertainty, and signal yield; it does not validate covariance or limits.



### Configured parameter starts and bounds



eps means np.finfo(float).eps.



| Model / parameter | Init | Bounds |

|---|---:|---:|

| All fits: signal_yield, background_yield | max(total?0.5, 1) each | [0, unbounded] |

| J/psi CB: mass, sigma, alpha, n | 3.0969; 0.015; 1.5; 3 | [2.8,3.4]; [eps,0.6]; [0.1,10]; [1.01,50] |

| J/psi exponential: slope | -1/0.6 = -1.6666667 | [-100,100] |

| psi(2S) Gaussian: mass, sigma | 3.6861; 0.01375 | [3.4,3.95]; [eps,0.55] |

| psi(2S) exponential: slope | -1/0.55 = -1.8181818 | [-100,100] |

| Upsilon triple Gaussian: offset, sigma, width_scale, frac_1s, frac_2s | 0; 0.0375; 1; 0.6; 0.25 | [-0.25,0.25]; [eps,3]; [0.2,5]; [0,1]; [0,1] |

| Upsilon Chebyshev-2: c1, c2 | 0; 0 | [-0.95,0.95] each |

| Z pseudo-Voigt: mass, sigma | 91.1876; 0.5 | [86,96]; [eps,10] |

| Z exponential: slope | -1/10 = -0.1 | [-100,100] |



Upsilon component masses are PDG spacings plus offset; frac_3s is derived and the fractions are normalized. In the pseudo-Voigt, sigma is the floating Gaussian detector resolution. Gamma is the fixed natural Lorentzian width: Z_WIDTH_GEV = 2.4955 GeV, gamma = Gamma/2 = 1.24775 GeV.



## D. Smoke-era comparison



No separate smoke fits.json/fits.parquet is present in data/results or tracked at CL2.0.6b; current full-statistics fits are the only available fit sidecar. Thus smoke masses, widths, uncertainties, chi2/ndf, and component yields are unavailable for numeric comparison. The prior Z window [70,110] is confirmed in CL2.0.6b; current window [86,96] is recorded below and must be accounted for when comparing Z entries.



| Resonance | Window | Mass | Stat unc. | Width | chi2/ndf | Signal yield | Background yield | Status |

|---|---|---:|---:|---:|---:|---:|---:|---|

| jpsi | [2.8,3.4] | 3.093694764 | 2.68295e-05 | 0.032584702 | 275.075 (25581.98/93) | 3592064.6 | 2335872.4 | valid |

| psi2s | [3.4,3.95] | 3.681045601 | 0.000215402 | 0.03624646 | 3.52515 (334.8897/95) | 153992.06 | 1268577.6 | valid |

| upsilon | [8.5,11.5] | 9.446802311 | 0.000353758 | 0.054660544 | 10.7975 (982.5692/91) | 493073.06 | 3925201.8 | valid |

| z | [86.0,96.0] | 90.89219983 | 0.00155209 | 0.0033341692 | 1291.02 (122647/95) | 3124683.6 | 2063098.3 | valid |



Available full gold rows/events: 83,057,658/42,812,309; supplied smoke counts: 1,324,707/1,034,022. Ratios are 62.70x pairs and 41.40x gold pair-bearing events. The supplied dataset statistics ratio is 59.51x. Current Z-window entries: 5,187,783. No missing smoke fit numbers are inferred.



## Part 1 decision



Both duplicate audits are exactly zero, so the audit gate allows Part 2. No production code or data files were changed during Part 1.


## Part 2 ? pre-change Z parameter confirmation

Before changing the model spec, inspection of src/physics/models.py confirmed that the Voigtian ModelSpec free parameter names are mass and sigma. In voigtian_pdf, sigma (GeV) is the Gaussian detector-resolution standard deviation: it appears in the Gaussian factor exp(-0.5 * (x/sigma)^2) and determines gaussian_fwhm = 2.354820045 * sigma. The Lorentzian natural width is not a free parameter: gamma = Z_WIDTH_GEV / 2 = 1.24775 GeV (fixed PDG Z_WIDTH_GEV = 2.4955 GeV). Only the Gaussian resolution sigma will receive the requested 1.5 GeV initial value and [0.3, 5.0] bounds; mass bounds and fixed Gamma are unchanged.


The pre-fix status-setting code was exactly:

    if not minuit.fmin.is_valid:
        raise RuntimeError(
            f"Fit failed for {resonance}: fmin={minuit.fmin}, values={_minuit_values(minuit)}"
        )
    ...
    return {
        ...
        "status": "valid",

This confirms the former status was convergence-only and otherwise assigned unconditionally.


## Part 2 implementation and verification

- Z Voigtian resolution sigma now initializes at 1.5 GeV and is bounded to [0.3, 5.0] GeV. The fixed Lorentzian natural width remains PDG Gamma_Z = 2.4955 GeV (gamma = 1.24775 GeV).
- Fit status follows the requested precedence: failed convergence, invalid_at_limit, invalid_covariance (inaccurate or non-positive-definite covariance), then valid. Fits include converged, parameter-limit and covariance flags. gof_flag is poor for chi2/ndf > 5 and ok otherwise; it does not alter status.
- The 2012 end-to-end synthetic fixtures now contain identifiable Crystal Ball signal plus background shapes, so the existing assert_valid_fit check exercises a valid J/psi fit under the stricter covariance/limit semantics.
- Verification on Windows: pytest 51 passed, 1 skipped; Ruff, compileall, and git diff --check passed. Linux execution was not available in this environment.
