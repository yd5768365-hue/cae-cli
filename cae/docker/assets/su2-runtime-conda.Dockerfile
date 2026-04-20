ARG MICROMAMBA_IMAGE=mambaorg/micromamba:1.5.10
FROM ${MICROMAMBA_IMAGE}

ARG SU2_VERSION=8.3.0

USER root
RUN micromamba install -y -n base -c conda-forge "su2=${SU2_VERSION}" \
    && micromamba clean -a -y

ENV PATH=/opt/conda/bin:${PATH}
WORKDIR /work

ENTRYPOINT ["SU2_CFD"]
CMD ["--help"]
