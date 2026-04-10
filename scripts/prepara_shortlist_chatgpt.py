#!/usr/bin/env python3

from _bootstrap import bootstrap_project


bootstrap_project()

from morpheus.chatgpt_research_prep import main


if __name__ == "__main__":
    raise SystemExit(main())
