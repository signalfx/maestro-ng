FROM alpine:3.2
MAINTAINER Arthur CARANTA <arthur@caranta.com>
ENV DEBIAN_FRONTEND noninteractive
ENV INITRD no
RUN apk update && apk add py-pip gcc python-dev linux-headers musl-dev
RUN pip install maestro-ng

ENTRYPOINT ["/usr/bin/maestro" ]
