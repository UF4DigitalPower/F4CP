# F4CP ADP Offline Training

The ADP page in F4CP captures UF4COM stream data and launches
`tools/adp_offline_train.py`.

The trainer expects these CSV columns:

```text
episode,step,vref_v,vin_v,vout_v,iin_a,iout_a,iref_applied_a
```

It exports a fixed-weight C header with the MCU-compatible `16x7` actor and
`16x8` critic shapes, plus a JSON report. The default GUI output is:

```text
Upper/STM32G474RBT6/USER/ADP_Scheduler/adp_outer_weights.h
```

Only deploy a model after checking the validation metrics and running a
current-limited hardware test. This is offline training; it does not enable
online learning in the power-control ISR.
