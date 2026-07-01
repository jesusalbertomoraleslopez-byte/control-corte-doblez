import streamlit as st; import pandas as pd; df=pd.DataFrame({'a':[1,2]}); st.dataframe(df, on_select='rerun', selection_mode='single-row')
