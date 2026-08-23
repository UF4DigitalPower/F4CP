# F4CP

F4CP can capture UF4COM power transitions and train the ADP outer-loop model
offline. Open the **ADP训练** page, collect or select a CSV dataset, set
`Ilimit`, `Epoch`, validation ratio, and seed, then export the generated
`adp_outer_weights.h`.

The default export path is:

```text
Upper/STM32G474RBT6/USER/ADP_Scheduler/adp_outer_weights.h
```

The STM32 firmware automatically uses that header when it is present. Online
training remains disabled by default. Review the generated JSON report and
perform current-limited hardware validation before deploying the model.
