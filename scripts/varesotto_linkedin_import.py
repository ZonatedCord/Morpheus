#!/usr/bin/env python3

from _bootstrap import bootstrap_project


bootstrap_project()

from finder_clienti_varesotto.varesotto_linkedin_import import LinkedInImporter


if __name__ == "__main__":
    LinkedInImporter().run()
