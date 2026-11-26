# Biến `tests/` thành package thường. Thiếu file này thì `tests` là namespace
# package, và mọi gói `tests` khác cài trong site-packages (Colab có sẵn một
# cái) sẽ thắng nó: `from tests.unit.core.test_knowledge import ...` gãy lúc collect.
