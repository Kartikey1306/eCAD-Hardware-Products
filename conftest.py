# pytest must not collect the eRadar360 factory-test CLI.
#
# eRadar360_CAD_Design/simulation/factory_test/eradar360_factory_test.py is a
# standalone argparse-driven factory tool, not a test suite. Its ten subsystem
# checks are named test_* and take a `demo` argument, so pytest collects them
# and errors at setup ("fixture 'demo' not found") — ten collection errors in
# a repo whose real tests all pass. (eCAD#21; cf. PR #22's __test__ = False
# approach — collect_ignore keeps the exclusion in test config instead of
# touching the factory tool.)
collect_ignore = [
    "eRadar360_CAD_Design/simulation/factory_test/eradar360_factory_test.py",
]
