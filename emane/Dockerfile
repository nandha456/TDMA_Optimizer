# EMANE 1.5.2 built from the official Adjacent Link source on Ubuntu 22.04.
#
# This is the same recipe as the prebuilt image used by run_demo.sh
# (lbitnetemu/emane:1.5.2, whose published build layers are reproduced here).
# Use it if you prefer not to depend on a third-party image:
#
#   docker build -t tdma-emane:1.5.2 emane/
#   EMANE_IMAGE=tdma-emane:1.5.2 emane/run_demo.sh
#
# Note: the experiments in docs/ were run with the prebuilt image; this
# Dockerfile was not built in the author's environment (no Ubuntu mirror access).

FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get -y update && apt-get -y install --no-install-recommends \
        git gcc g++ autoconf automake libtool dh-python debhelper python3-setuptools \
        libxml2-dev libprotobuf-dev libpcap-dev libpcre3-dev uuid-dev pkg-config \
        python3-protobuf protobuf-compiler python3-lxml python3-zmq \
        iputils-ping net-tools util-linux ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt
RUN git clone https://github.com/adjacentlink/emane -b v1.5.2 \
    && cd emane && ./autogen.sh && ./configure && make deb \
    && mkdir -p /opt/built && cp $(find .debbuild -name "*.deb") /opt/built \
    && apt-get -y update \
    && (dpkg -i /opt/built/python3*.deb /opt/built/emane*.deb || apt-get -y install -f) \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
CMD ["bash"]
