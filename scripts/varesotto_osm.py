#!/usr/bin/env python3

from _bootstrap import bootstrap_project


bootstrap_project()

from morpheus.varesotto_osm import main


if __name__ == "__main__":
    raise SystemExit(main())
