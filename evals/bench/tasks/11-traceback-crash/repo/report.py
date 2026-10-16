import sys

from sales.io import load_orders
from sales.render import render
from sales.summary import summarize

if __name__ == "__main__":
    print(render(summarize(load_orders(sys.argv[1]))))
