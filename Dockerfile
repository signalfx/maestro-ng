FROM alpine:3.10
MAINTAINER Arthur CARANTA <arthur@caranta.com>

ENV DEBIAN_FRONTEND=noninteractive INITRD=no
RUN apk update && apk add py-pip gcc python-dev linux-headers musl-dev && rm -rf /var/cache/apk/*

ADD . /opt/maestro-ng
RUN pip install -e /opt/maestro-ng

ENTRYPOINT ["/usr/bin/maestro" ]
