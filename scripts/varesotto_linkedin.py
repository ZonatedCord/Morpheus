#!/usr/bin/env python3

from _bootstrap import bootstrap_project


bootstrap_project()

from finder_clienti_varesotto.varesotto_linkedin import LinkedInClientFinder


if __name__ == "__main__":
    LinkedInClientFinder().run()
