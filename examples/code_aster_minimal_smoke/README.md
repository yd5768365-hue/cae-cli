Minimal Code_Aster smoke case verified through `cae docker run`.

This example uses a direct `.comm` input because the Code_Aster `run_aster`
launcher supports running command files directly after the container activation
script is sourced.

Run it from the repository root:

```bash
cae docker pull code-aster
cae docker run code-aster examples/code_aster_minimal_smoke/case.comm -o results/code-aster-smoke
```

Expected output includes `docker-code_aster.log`.
