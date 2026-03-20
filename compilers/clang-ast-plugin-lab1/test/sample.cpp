int sum(int a, int b);

static double scale(double value, double factor) {
  return value * factor;
}

int sum(int a, int b) {
  return a + b;
}

int main() {
  return sum(2, 3) + static_cast<int>(scale(1.5, 2.0));
}
