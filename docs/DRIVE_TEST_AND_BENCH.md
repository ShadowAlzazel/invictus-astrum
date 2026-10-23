PAPILION VENATRIX  --  D-He3 in LiD,  phi 0.429  eta 0.785  f 0.45
==============================================================================
  Dry mass              50,000 t
  Propellant            23,078 t
    capsule fuel        10,385 t
      He3 (60%)         6,231 t
      deuterium         4,154 t
    LiD tamper          12,693 t
  Full load             73,078 t
  Mass ratio R          1.462

  Fuel ceiling, f=1     26,533 km/s  (perfect burn+nozzle)
  Exhaust velocity      10,539 km/s
    LiD bonus           +13.7% on jet energy  (n-fraction 2.0%, Z=2)
  DELTA-V               4,000 km/s   (1.33% c)
  Mass efficiency       5.77 t propellant per km/s

  Acceleration          0.40 g = 3.923 m/s2
  Thrust, full load     286.7 MN
  Jet power             1.5 PW
  Mass flow             27.2 kg/s
  Full burn time        11.80 d
  Jet energy            1.3 ZJ  (306 Gt TNT)

  Antiprotons           1.737 mg   (46.8% of bunker)
  BURNS PER BUNKER      2.14
  Tank volume           68,198 m3

DRIVE BLOCK  --  2 x 7 = 14 engines @ 10 Hz
==============================================================================
  Thrust per engine     20.5 MN
  Power per engine      107.9 TW
  Pellet mass           0.19 kg
  Energy per pulse      10.8 TJ  (2,578.9 t TNT)
  Pulses per engine     10,196,385
  Ship pulse rate       140 Hz  (phased)

RATING vs CAPABILITY  --  rated 3,000 km/s on a 4,000 km/s tank
==============================================================================
  Energy, full tank     1.3 ZJ  (306 Gt TNT)
  Energy to 3,000 km/s  1.0 ZJ  (240 Gt TNT)
  Energy in reserve     276.3 EJ  (21.6% of tank)

  Propellant spent      18,103 t
  Propellant reserve    4,975 t  (0.374 mg p-bar held back)
  Burn to rated dv      8.85 d

THERMAL
==============================================================================
  Jet power             1.5 PW
  Raw pickup @ 1.0e-03  1.5 TW   (into the loop)
  Hull leak @ 6.0e-07   906.4 MW   (out of the loop)
  Mane capacity         1.0 GW   OK, 9.4% margin

  MAX ALLOWED LEAK      6.62e-07  = 0.662 ppm of jet power
  LOOP MUST RETURN      99.9338% of raw pickup
  Mane area needed      1,523 m2 at 1,800 K
  Store endurance       10.8 TJ never fills -- mane holds

TAMPER BONUS  --  neutron fraction sweep at f 0.45
==============================================================================
  n-frac       bonus       v_e    prop t    full t   pbar mg   burns   t/km/s
------------------------------------------------------------------------------
  0.000        0.0%     9,885    17,729    67,729     1.334    2.78     5.91
  0.010        6.8%    10,217    17,064    67,064     1.284    2.89     5.69
  0.020       13.7%    10,539    16,465    66,465     1.239    3.00     5.49
  0.035       23.9%    11,005    15,670    65,670     1.179    3.15     5.22
  0.050       34.2%    11,451    14,975    64,975     1.127    3.29     4.99
  0.080       54.7%    12,296    13,817    63,817     1.040    3.57     4.61
  (all rows hold dv = 3,000 km/s; n-frac 0 = dead tamper)

MARK LADDER (A)  --  SAME SHIP, SAME TANK.  What each mark reaches.
==============================================================================
  mark                     phi   eta      k   v_e km/s  DELTA-V km/s   vs Mk I   burn d
------------------------------------------------------------------------------
  Mk I    first pattern   0.33  0.70  0.231      8,729         3,313     +0.0%     9.77
  Mk II   Old Forest      0.38  0.75  0.285      9,695         3,679    +11.1%    10.86
  Mk II-C conversion      0.38  0.80  0.304     10,013         3,800    +14.7%    11.21
  Mk II.7 modern          0.43  0.79  0.337     10,539         4,000    +20.7%    11.80
  Mk III  yard trial      0.45  0.80  0.360     10,897         4,135    +24.8%    12.20
  Mk IV   test stand      0.55  0.84  0.462     12,344         4,685    +41.4%    13.82
     ceiling ◇            0.60  0.85  0.510     12,970         4,922    +48.6%    14.52
  (mix f 0.45, propellant 23,078 t, dry 50,000 t, 0.40 g -- only the mark changes)

MARK LADDER (B)  --  ALL HELD AT 3,000 km/s.  What each mark costs.
==============================================================================
  mark                        k   prop t  TAMPER t   fuel t   He3 t  pbar mg   burns
------------------------------------------------------------------------------
  Mk I    first pattern   0.231   20,507    11,279    9,228   5,537    1.544    2.40
  Mk II   Old Forest      0.285   18,132     9,973    8,159   4,896    1.365    2.72
  Mk II-C conversion      0.304   17,466     9,606    7,860   4,716    1.315    2.82
  Mk II.7 modern          0.337   16,465     9,056    7,409   4,446    1.239    3.00
  Mk III  yard trial      0.360   15,847     8,716    7,131   4,279    1.193    3.11
  Mk IV   test stand      0.462   13,755     7,565    6,190   3,714    1.035    3.59
     ceiling ◇            0.510   13,012     7,157    5,856   3,513    0.979    3.79
  (every hull runs the SAME mix f 0.45 -- standardised stores. The mark buys reserve, not mixture.)

DELTA-V (km/s)  --  rows = mix f, cols = propellant t, dry 50,000 t
==============================================================================
  f               10k        25k        50k        75k       100k       150k
------------------------------------------------------------------------------
  0.100           983      2,187      3,738      4,942      5,925      7,477
  0.150         1,193      2,653      4,535      5,995      7,188      9,070
  0.205         1,379      3,067      5,243      6,931      8,310     10,486
  0.300         1,633      3,632      6,209      8,208      9,842     12,419
  0.350         1,742      3,875      6,625      8,757     10,500     13,249
  0.400         1,838      4,088      6,988      9,238     11,076     13,976
  0.500         1,994      4,433      7,579     10,019     12,013     15,158
  0.600         2,104      4,679      7,999     10,575     12,679     15,999
  0.750         2,175      4,837      8,270     10,932     13,107     16,539

MIX LADDER  --  propellant solved to hold 3,000 km/s
==============================================================================
  f             v_e  tamper t   fuel t    full t  pbar mg  burns      P jet    vol m3
------------------------------------------------------------------------------
  0.100       5,393    33,485    3,721    87,206    0.622   5.96   922.5 TW    61,533
  0.150       6,543    24,724    4,363    79,087    0.730   5.09     1.0 PW    53,512
  0.205       7,564    19,350    4,990    74,339    0.835   4.45     1.1 PW    49,755
  0.300       8,958    13,922    5,967    69,889    0.998   3.72     1.2 PW    47,683
  0.350       9,557    11,984    6,453    68,438    1.079   3.44     1.3 PW    47,631
  0.400      10,082    10,397    6,932    67,329    1.159   3.20     1.3 PW    47,988
  0.500      10,934     7,892    7,892    65,785    1.320   2.81     1.4 PW    49,581
  0.600      11,541     5,937    8,906    64,843    1.490   2.49     1.5 PW    52,142
  0.750      11,931     3,574   10,721    64,295    1.793   2.07     1.5 PW    58,187

TRANSITS  --  brachistochrone at 0.40 g,  budget 4,000 km/s
==============================================================================
  leg                       distance        time    dv km/s   % budget
------------------------------------------------------------------------------
  Core picket               0.002 AU      4.86 h       68.6      1.72%
  Cislunar                  0.003 AU      5.50 h       77.7      1.94%
  Long picket               0.013 AU     12.54 h      177.1      4.43%
  Earth-Mars, min           0.521 AU      3.26 d    1,106.3     27.66%
  1 AU                      1.000 AU      4.52 d    1,532.1     38.31%
  Earth-Jupiter, min        3.930 AU      8.96 d    3,037.4     75.94%