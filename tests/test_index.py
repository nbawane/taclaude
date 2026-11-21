from datetime import date

from niftyta.data.index_provider import fetch_index_day

HEADER = ("Index Name,Index Date,Open Index Value,High Index Value,Low Index Value,"
          "Closing Index Value,Points Change,Change(%),Volume,Turnover (Rs. Cr.),P/E,P/B,Div Yield")


def write(tmp_path, day_str, close=17599.15):
    f = tmp_path / f"ind_close_all_{day_str}.csv"
    f.write_text("\n".join([HEADER, f"Nifty 50,{day_str},1,2,0.5,{close},0,0,1,1,1,1,1"]))
    return f


def test_month_first_stamp_is_accepted(tmp_path):
    write(tmp_path, "04-06-2023")  # 6 April 2023, stamped month-first by NSE
    df = fetch_index_day(date(2023, 4, 6), raw_dir=tmp_path, pause=0)
    assert df is not None and df["date"].iloc[0].date() == date(2023, 4, 6)


def test_previous_session_file_is_a_closed_day(tmp_path):
    f = tmp_path / "ind_close_all_20230406.csv"  # the 6 April file, but stamped with 5 April
    f.write_text("\n".join([HEADER, "Nifty 50,05-04-2023,1,2,0.5,17557.05,0,0,1,1,1,1,1"]))
    assert fetch_index_day(date(2023, 4, 6), raw_dir=tmp_path, pause=0) is None
